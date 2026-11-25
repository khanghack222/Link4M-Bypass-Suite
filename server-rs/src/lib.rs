//! Library surface for `bypass-server`.
//!
//! `main.rs` stays a thin bootstrap; everything testable lives here so the
//! integration tests can build the router without spawning a process.

pub mod api;
pub mod config;
pub mod engine;
pub mod fast_decode;
pub mod providers;
pub mod state;
