//! Minimal Chrome DevTools Protocol client over a single page WebSocket.
//!
//! One writer/reader task owns the socket; requests are correlated by id and
//! completed through oneshot channels. No protocol codegen, no extra layers.

use anyhow::{anyhow, Result};
use futures_util::{SinkExt, StreamExt};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, AtomicI64, Ordering};
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::{mpsc, oneshot, Mutex};
use tokio_tungstenite::tungstenite::Message;

type Pending = Arc<Mutex<HashMap<i64, oneshot::Sender<std::result::Result<Value, String>>>>>;

pub struct Cdp {
    tx: mpsc::UnboundedSender<Value>,
    pending: Pending,
    next_id: AtomicI64,
    closed: AtomicBool,
}

impl Cdp {
    pub async fn connect(ws_url: &str) -> Result<Arc<Self>> {
        let (stream, _) = tokio_tungstenite::connect_async(ws_url).await?;
        let (mut write, mut read) = stream.split();
        let (out_tx, mut out_rx) = mpsc::unbounded_channel::<Value>();
        let pending: Pending = Arc::new(Mutex::new(HashMap::new()));
        let pending_reader = pending.clone();

        tokio::spawn(async move {
            loop {
                tokio::select! {
                    outgoing = out_rx.recv() => {
                        let Some(value) = outgoing else { break };
                        if write.send(Message::Text(value.to_string().into())).await.is_err() {
                            break;
                        }
                    }
                    incoming = read.next() => {
                        match incoming {
                            Some(Ok(Message::Text(text))) => {
                                let Ok(value) = serde_json::from_str::<Value>(&text) else { continue };
                                let Some(id) = value.get("id").and_then(Value::as_i64) else { continue };
                                let Some(sender) = pending_reader.lock().await.remove(&id) else { continue };
                                let outcome = match value.get("error") {
                                    Some(err) => Err(err.to_string()),
                                    None => Ok(value.get("result").cloned().unwrap_or(Value::Null)),
                                };
                                let _ = sender.send(outcome);
                            }
                            Some(Ok(_)) => {}
                            _ => break,
                        }
                    }
                }
            }
            // Fail every request still waiting so callers never hang.
            for (_, sender) in pending_reader.lock().await.drain() {
                let _ = sender.send(Err("cdp connection closed".into()));
            }
        });

        Ok(Arc::new(Self {
            tx: out_tx,
            pending,
            next_id: AtomicI64::new(1),
            closed: AtomicBool::new(false),
        }))
    }

    pub async fn call(&self, method: &str, params: Value) -> Result<Value> {
        if self.closed.load(Ordering::Relaxed) {
            return Err(anyhow!("cdp closed"));
        }
        let id = self.next_id.fetch_add(1, Ordering::Relaxed);
        let (sender, receiver) = oneshot::channel();
        self.pending.lock().await.insert(id, sender);
        let message = json!({"id": id, "method": method, "params": params});
        if self.tx.send(message).is_err() {
            self.pending.lock().await.remove(&id);
            return Err(anyhow!("cdp writer gone"));
        }
        match tokio::time::timeout(Duration::from_secs(30), receiver).await {
            Ok(Ok(Ok(value))) => Ok(value),
            Ok(Ok(Err(err))) => Err(anyhow!("{method}: {err}")),
            Ok(Err(_)) => Err(anyhow!("{method}: response dropped")),
            Err(_) => {
                self.pending.lock().await.remove(&id);
                Err(anyhow!("{method}: timeout"))
            }
        }
    }

    /// Evaluate JS in the main frame (no context) or in an isolated world.
    pub async fn eval(&self, context_id: Option<i64>, expression: &str) -> Result<Value> {
        let mut params = json!({
            "expression": expression,
            "returnByValue": true,
            "awaitPromise": true,
            "userGesture": true,
        });
        if let Some(id) = context_id {
            params["contextId"] = json!(id);
        }
        let reply = self.call("Runtime.evaluate", params).await?;
        if let Some(exception) = reply.get("exceptionDetails") {
            let text = exception
                .get("exception")
                .and_then(|e| e.get("description"))
                .and_then(Value::as_str)
                .or_else(|| exception.get("text").and_then(Value::as_str))
                .unwrap_or("js error");
            return Err(anyhow!("js: {}", text.chars().take(200).collect::<String>()));
        }
        Ok(reply
            .get("result")
            .and_then(|r| r.get("value"))
            .cloned()
            .unwrap_or(Value::Null))
    }

    pub fn close(&self) {
        self.closed.store(true, Ordering::Relaxed);
    }
}

impl Drop for Cdp {
    fn drop(&mut self) {
        self.closed.store(true, Ordering::Relaxed);
    }
}
