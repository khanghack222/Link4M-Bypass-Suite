(function() {
	var traffic_key = '4AzF9IZh9';
	var apiUrl = 'https://api.layma.net';
	var hCaptchaSiteKey = 'your-hcaptcha-site-key';
	var hCaptchaTokenDefault = '';
	var captchaProvider = 'qcaptcha'.toLowerCase();
	var captchaLaAppKey = 'app_38bff39ed2ebe6cd5a1d5f6d321210af';
	var captchaLaAction = 'getcode';
	var captchaLaLang = 'vi';
	var captchaLaProduct = 'float';
	var captchaLaForceType = 'click_shape';
	var captchaLaTheme = 'light';
	var captchaLaDifficulty = 'normal';
	var qCaptchaSiteKey = 'd0c97bcc-d88c-42d1-8a0c-1180bf53e2a1';
	var qCaptchaScriptUrl = 'https://js.103-141-140-153.sslip.io/api.js';
	var qCaptchaDomains = ["vijaylaxmigranito.in","www.vijaylaxmigranito.in","matlamafc.com","onlinejob.com.co","www.onlinejob.com.co","1bellanarithebrand.com.co","rubensbits.co","sunwinkt.com","sunwinvv.com","sunwinmb.com","sunwinbv.com","black-sheep.com.co","bituplast.com.co","go88en.com","go88yt.com","go88gh.com","smileitsolutions.co.in","agilafc.com","www.agilafc.com"];
	var traffic_id = '';
	var traffic_campain_domain = '';
	var traffic_use_qcaptcha = false;
	var cache_traffic_session = "cache_traffic_session_" + traffic_key;
	var traffic_session_token = window.localStorage.getItem(cache_traffic_session) || '';
	var widgetSessionStorageKey = "layma_widget_session_" + traffic_key;
	var widgetSessionToken = null;
	try {
		widgetSessionToken = window.sessionStorage.getItem(widgetSessionStorageKey) || null;
	} catch (e) {
		widgetSessionToken = null;
	}
	var widgetSessionWaiters = null;
	var traffic_domain = 's1.what-on.com';
	var cache_time = "cache_remain_time_" + traffic_key;
	var cache_solution = "cache_solution_" + traffic_key;
	var count_step = "count_step_" + traffic_key;
	var cache_flatform = "cache_flatform_" + traffic_key;
	var initTrafficScript = initTrafficScript || {};
	var traffic_wait_time = 300;
	var minTimeOnSiteSeconds = parseInt('10', 10) || 10;
	var campaignTimeOnSite = 0;
	var serverRequiredWaitSeconds = 0;
	function randomIntInclusive(min, max) {
		return Math.floor(Math.random() * (max - min + 1)) + min;
	}
	function alignWaitWithServer() {
		var required = Math.max(0, minTimeOnSiteSeconds, campaignTimeOnSite, serverRequiredWaitSeconds);
		if (!(traffic_wait_time >= required)) {
			traffic_wait_time = required;
		}
	}
	function parseRemainMs(value) {
		var n = parseInt(value, 10);
		if (!isFinite(n)) {
			return 0;
		}
		return Math.max(0, n);
	}
	function remainSecondsFromMs(ms) {
		return Math.max(0, Math.floor(parseRemainMs(ms) / 1000));
	}
	function clampRemainSeconds(value) {
		var n = Number(value);
		if (!isFinite(n)) {
			return 0;
		}
		return Math.max(0, Math.floor(n));
	}

	var nativeFnToString = Function.prototype.toString;
	var nativePerfNow = (function() {
		try {
			var fn = Performance.prototype.now;
			if (typeof fn === 'function') {
				return function() { return fn.call(performance); };
			}
		} catch (e) {}
		return function() { return performance.now(); };
	})();
	var speedHackBlocked = false;
	var speedHackWatchStarted = false;
	var waitRemainAtAnchor = 0;
	var waitAnchorPerf = 0;
	var waitPauseAt = 0;
	var waitPauseMs = 0;
	var speedHackMessage = 'Phát hiện công cụ tăng tốc. Vui lòng tắt extension rồi tải lại trang.';

	function realNow() {
		try { return nativePerfNow(); } catch (e) { return performance.now(); }
	}

	function isNativeFn(fn) {
		if (typeof fn !== 'function') return false;
		try {
			return /\[native code\]/.test(nativeFnToString.call(fn));
		} catch (e) {
			return false;
		}
	}

	function hasTurboOverlay() {
		try {
			return !!(document.getElementById('mp-panel')
				|| document.getElementById('mp-speed-css')
				|| document.getElementById('mp-toggle-btn')
				|| document.getElementById('mp-slider'));
		} catch (e) {
			return false;
		}
	}

	function hasTurboGlobals() {
		try {
			if (window.__MP_L) return true;
			var mp = window.MP;
			if (mp && (typeof mp.tg === 'function' || typeof mp.on === 'function' || typeof mp.tb === 'function')) {
				return true;
			}
		} catch (e) {}
		return false;
	}

	function hasSpoofedClock() {
		try {
			if (!isNativeFn(Date.now)) return true;
			var origin = (typeof performance.timeOrigin === 'number') ? performance.timeOrigin : 0;
			if (!origin) return false;
			return Math.abs(Date.now() - (origin + realNow())) > 4000;
		} catch (e) {
			return false;
		}
	}

	function detectSpeedHack() {
		return hasTurboOverlay() || hasTurboGlobals() || hasSpoofedClock();
	}

	function freezeForSpeedHack() {
		if (speedHackBlocked) return;
		speedHackBlocked = true;
		try {
			if (typeof updateTrackingMessage === 'function') {
				updateTrackingMessage(speedHackMessage);
			}
			var btn = document.getElementById('xacthucButton');
			if (btn) btn.style.display = 'none';
			var el = document.getElementById(traffic_key);
			if (el) {
				el.dataset.time = String(Math.max(1, Math.ceil(getServerWaitRemainingSeconds())));
			}
		} catch (e) {}
	}

	function haltIfSpeedHack() {
		if (speedHackBlocked) return true;
		if (detectSpeedHack()) {
			freezeForSpeedHack();
			return true;
		}
		return false;
	}

	function startSpeedHackWatch() {
		if (speedHackWatchStarted) return;
		speedHackWatchStarted = true;
		haltIfSpeedHack();
		setInterval(function() { haltIfSpeedHack(); }, 1000);
	}

	function bindWaitClockFromServer(result, isFirstPage) {
		var remaining = result && result.remainingWaitSeconds;
		if (typeof remaining !== 'number' || remaining < 0) {
			remaining = (result && result.requiredWaitSeconds) || serverRequiredWaitSeconds || 0;
		}
		if (isFirstPage && remaining <= 0) {
			remaining = Math.max(remaining, serverRequiredWaitSeconds, minTimeOnSiteSeconds);
		}
		waitRemainAtAnchor = Math.max(0, remaining);
		waitAnchorPerf = realNow();
		waitPauseAt = 0;
		waitPauseMs = 0;
	}

	function getServerWaitRemainingSeconds() {
		if (!waitAnchorPerf) {
			return 0;
		}
		var now = realNow();
		if (traffic_blurred) {
			if (!waitPauseAt) waitPauseAt = now;
		} else if (waitPauseAt) {
			waitPauseMs += now - waitPauseAt;
			waitPauseAt = 0;
		}
		var marked = waitPauseAt ? waitPauseAt : now;
		return Math.max(0, waitRemainAtAnchor - (marked - waitAnchorPerf - waitPauseMs) / 1000);
	}

	function hasCompletedServerWait() {
		if (speedHackBlocked) return false;
		if (!waitAnchorPerf) return true;
		return getServerWaitRemainingSeconds() <= 0;
	}

	function isGetCodeWaitSatisfied(element) {
		if (haltIfSpeedHack()) return false;
		if (element && clampRemainSeconds(element.dataset.time) > 0) return false;
		if (!hasCompletedServerWait()) return false;
		return true;
	}

	function canOpenGetCode(element) {
		if (!isGetCodeWaitSatisfied(element)) return false;
		if (!element) return false;
		if (element.dataset.loading === 'true') return false;
		if (element.dataset.click !== 'true') return false;
		if (element.dataset.loaded !== undefined) return false;
		return true;
	}

	function createWaitState(initialMs) {
		var total = parseRemainMs(initialMs);
		return {
			totalMs: total,
			origin: realNow(),
			pauseAt: 0,
			pauseMs: 0,
			prevMs: total
		};
	}

	function readWaitRemaining(state, ignoreBlur) {
		var now = realNow();
		var blurred = !ignoreBlur && traffic_blurred;
		if (blurred) {
			if (!state.pauseAt) state.pauseAt = now;
			return state.prevMs;
		}
		if (state.pauseAt) {
			state.pauseMs += now - state.pauseAt;
			state.pauseAt = 0;
		}
		return Math.max(0, state.totalMs - (now - state.origin - state.pauseMs));
	}

	function reachedWaitMark(timeInMs, targetMs, prevMs) {
		targetMs = parseRemainMs(targetMs);
		timeInMs = parseRemainMs(timeInMs);
		prevMs = parseRemainMs(prevMs);
		if (prevMs <= targetMs) return false;
		return timeInMs <= targetMs;
	}

	function startWaitTicker(options) {
		var state = options.state;
		var show_code_button = options.button;
		var element = options.element;
		var ignoreBlur = !!options.ignoreBlur;
		var onComplete = options.onComplete;
		var onZero = options.onZero;
		var onTick = options.onTick;
		var timerInterval = setInterval(function() {
			if (haltIfSpeedHack()) {
				clearInterval(timerInterval);
				return;
			}
			var prevMs = state.prevMs;
			var timeInMs = readWaitRemaining(state, ignoreBlur);
			if (!ignoreBlur && traffic_blurred) return;
			var timeInSeconds = remainSecondsFromMs(timeInMs);
			updateButtonDisplay(show_code_button, element, timeInSeconds);
			if (onTick) onTick(timeInMs, timeInSeconds);
			var done = onComplete && onComplete(timeInMs, timeInSeconds, prevMs);
			state.prevMs = timeInMs;
			if (done) {
				clearInterval(timerInterval);
				return;
			}
			if (timeInMs <= 0) {
				clearInterval(timerInterval);
				if (onZero) onZero();
			}
		}, 250);
		return timerInterval;
	}
	var timeToScrollUp = 0;
	var timeToScrollDown = 0;

	var timeToScrollUp2 = 0;
	var timeToScrollUpS4 = 0;
	var timeToScrollDownS4 = 0;
	var timeToScrollUpS4_2 = 0;

	var timeSangManHinh = 25;
	let timeSangNewS4 = 15;
	var timeSangManHinhNew = 10;
	var timeSangManHinhS4 = 0;
	var timeSangManHinhS5 = 0;

	var traffic_blurred = !1;;
	var hidden = "hidden";
	let trackingMessageContainer;
	let elementToClickScreenContainer;
	var referrer_pattern_FB = '^http(s|)\:\/\/(www|l|m|lm|mobile|web|touch|fbclid|)(\.)?facebook\.[a-z]{2,3}([.a-z]{2,4}|)';
	var referrer_pattern_GG = '^http(s|)\:\/\/(?:www\.)?google\.[a-z]{2,3}([.a-z]{2,4}|)';
	var referrer_pattern_INS = '^http(s|)\:\/\/(www|l|m|lm|mobile|web|touch|fbclid|)(\.)?instagram\.[a-z]{2,3}([.a-z]{2,4}|)';
	var referrer_pattern_YOUTUBE = '^http(s|)\:\/\/(www|l|m|lm|mobile|web|touch|)(\.)?youtube\.[a-z]{2,3}([.a-z]{2,4}|)';
	var referrer_pattern_CF = '^http(s|)\:\/\/(www|l|m|lm|mobile|web|touch|)(\.)?youtube\.[a-z]{2,3}([.a-z]{2,4}|)';

	var check_ref = false;
	var get_code = true;

	var get_code_string = 'LẤY MÃ';
	var get_code_after_string = 'Lấy mã sau';
	var code_string = 'Mã Code';
	var copied_notify = 'Đã sao chép mã';
	var close_private_mode_message = 'Vui lòng tắt chế độ Ẩn danh để tiếp tục. Xin cảm ơn !';
	function showPrivateModeMessage(element) {
		if (!element) {
			return;
		}
		var notice = document.createElement("div");
		notice.textContent = close_private_mode_message;
		notice.style.display = "block";
		notice.style.width = "100%";
		notice.style.maxWidth = "100%";
		notice.style.boxSizing = "border-box";
		notice.style.background = "#c40b11";
		notice.style.color = "#fff";
		notice.style.fontWeight = "700";
		notice.style.fontSize = "14px";
		notice.style.lineHeight = "1.45";
		notice.style.padding = "10px 12px";
		notice.style.margin = "5px 0";
		notice.style.borderRadius = "7px";
		notice.style.textAlign = "center";
		notice.style.whiteSpace = "normal";
		notice.style.wordBreak = "break-word";
		element.innerHTML = "";
		element.appendChild(notice);
	}
	function applyPrivateModeIfNeeded(element, result) {
		if (result && result.isPrivate) {
			showPrivateModeMessage(element);
			return true;
		}
		return false;
	}
	var requiredScrollUp = 'Vui lòng cuộn lên để tiếp tục lấy mã';
	var requiredScrollDown = 'Vui lòng cuộn xuống để tiếp tục lấy mã';
	var requiredClickPost = 'Vui lòng nhấn bài viết bất kỳ sau đó kéo xuống dưới cùng để lấy mã(Click đủ 2 lần bài viết sẽ có mã)';
	var requiredClickPost1 = 'Vui lòng nhấn bài viết bất kỳ sau đó kéo xuống dưới cùng để lấy mã(Chỉ cần click 1 lần bài viết nữa sẽ có mã)';
	var requiredClickPostSolution2 = 'Vui lòng nhấn bài viết bất kỳ sau đó kéo xuống dưới cùng để lấy mã(Chỉ cần click 1 lần bài viết sẽ có mã)';
	var loaded_script = false;

	function buildCampainUrl(flatform, waitMode, requiredPageVisits, isContinuation) {
		var params = "keytoken=" + encodeURIComponent(traffic_key)
			+ "&flatform=" + encodeURIComponent(flatform)
			+ "&waitMode=" + waitMode
			+ "&requiredPageVisits=" + requiredPageVisits;
		if (isContinuation) {
			var existingToken = window.localStorage.getItem(cache_traffic_session);
			if (existingToken) {
				params += "&sessionToken=" + encodeURIComponent(existingToken);
			}
		}
		return apiUrl + "/api/admin/campain?" + params;
	}

	function applyServerWaitSession(result, isFirstPage) {
		if (result.trafficSessionToken) {
			traffic_session_token = result.trafficSessionToken;
			window.localStorage.setItem(cache_traffic_session, result.trafficSessionToken);
		}
		if (result.domain) {
			traffic_campain_domain = result.domain;
		}
		traffic_use_qcaptcha = !!result.useQCaptcha;
		if (result.requiredWaitSeconds > 0) {
			serverRequiredWaitSeconds = result.requiredWaitSeconds;
		}
		alignWaitWithServer();
		bindWaitClockFromServer(result, isFirstPage);
		pingCampaignVisit(result);
	}

	function pingCampaignVisit(result) {
		if (!result || !result.trafficSessionToken || !result.visitTicket || !result.id) {
			return;
		}
		ajaxPost(
			apiUrl + "/api/traffic/visit",
			{
				trafficSessionToken: result.trafficSessionToken,
				visitTicket: result.visitTicket,
				trafficId: result.id
			},
			function(updated) {
				if (updated && updated.visitTicket) {
					result.visitTicket = updated.visitTicket;
				}
			}
		);
	}


	if (hidden in document)
		document.addEventListener("visibilitychange", onchange);
	else if ((hidden = "mozHidden") in document)
		document.addEventListener("mozvisibilitychange", onchange);
	else if ((hidden = "webkitHidden") in document)
		document.addEventListener("webkitvisibilitychange", onchange);
	else if ((hidden = "msHidden") in document)
		document.addEventListener("msvisibilitychange", onchange);
	// IE 9 and lower:
	else if ("onfocusin" in document)
		document.onfocusin = document.onfocusout = onchange;
	// All others:
	else
		window.onpageshow = window.onpagehide = window.onfocus = window.onblur = onchange;
	// Localize jQuery variable
	var jQuery;

	if (!isFirstLoad(initTrafficScript)) {
		return;
	}
	/******** Load jQuery if not present *********/
	if (window.jQuery === undefined || window.jQuery.fn === undefined || window.jQuery.fn.jquery !== '3.6.0') {

		var script_tag = document.createElement('script');
		script_tag.setAttribute("type","text/javascript");
		script_tag.setAttribute("src",
			"https://ajax.googleapis.com/ajax/libs/jquery/3.6.0/jquery.min.js");
		if (script_tag.readyState) {
		  script_tag.onreadystatechange = function () {
			  if (this.readyState == 'complete' || this.readyState == 'loaded') {
				  scriptTrafficLoadHandler();
			  }
		  };
		} else {
		  script_tag.onload = scriptTrafficLoadHandler;
		}
		// Try to find the head, otherwise default to the documentElement
		(document.getElementsByTagName("head")[0] || document.documentElement).appendChild(script_tag);
	} else {
		// The jQuery version on the window is the one we want to use
		jQuery = window.jQuery;
		traffic_main();
	}

	/******** Called once jQuery has loaded ******/
	function scriptTrafficLoadHandler() {
		jQuery = window.jQuery.noConflict(true);
		traffic_main();
	}
	const getReferrerByFbclid = () => {
		let url = new URL(location.href)

		if (url.searchParams.has('fbclid')) {
			return 'https://fbclid.facebook.com';
		}

		return null
	}
	const getReferrer = () => {
		let referrer = document.referrer

		if (!referrer) {
			referrer = getReferrerByFbclid()
		}
		console.log("referrer = " + referrer);

		return referrer
	}
	const checkReferer = (referrer) =>{
		if (!referrer) {
			return 'tructiep';
		}
		if(referrer === undefined || referrer == 'undefined'){
			return 'tructiep';
		}
		if(referrer === null){
			return 'tructiep';
		}
		var regexGG = new RegExp(referrer_pattern_GG,"i");
		if (referrer.match(regexGG)) {
			return 'google';
		}
		var regexFB = new RegExp(referrer_pattern_FB,"i");
		if (referrer.match(regexFB)) {
			return 'facebook';
		}
		var regexINS = new RegExp(referrer_pattern_INS,"i");
		if (referrer.match(regexINS)) {
			return 'instagram';
		}
		var regexYOUTUBE = new RegExp(referrer_pattern_YOUTUBE,"i");
		if (referrer.match(regexYOUTUBE)) {
			return 'youtube';
		}
		let hostname = window.location.hostname;
		console.log("Current hostname:", hostname);
		if (referrer.indexOf(hostname) !== -1) {
			return 'clicklink';
		}
		return 'tructiep';
	}
	const ajax = function(url, method = 'GET', data, onSuccess = null, onError = null, onDone = null) {
		let postData = JSON.stringify(data);
		let xhr = new XMLHttpRequest();

		xhr.open(method, url, true);
		xhr.setRequestHeader('Content-type', 'application/json; charset=UTF-8');
		if (widgetSessionToken) {
			xhr.setRequestHeader('X-Traffic-Session', widgetSessionToken);
		}
		xhr.send(postData);

		xhr.addEventListener('load', function(event) {
			var status = event.target.status;
			var raw = event.target.response;
			var parsed = null;
			try {
				parsed = raw ? JSON.parse(raw) : null;
			} catch (e) {
				parsed = raw;
			}
			if (status >= 200 && status < 300) {
				if (onSuccess) onSuccess(parsed);
			} else if (onError) {
				onError({ status: status, response: parsed, raw: raw });
			}
			if (onDone) onDone();
		});

		xhr.addEventListener('error', function(event) {
			if (onError) onError(event);
			if (onDone) onDone();
		});
	}

	const ajaxGet = function(url, onSuccess = null, onError = null, onDone = null) {
		return ajax(url, 'GET', [], onSuccess, onError, onDone);
	}

	const ajaxPost = function(url, data, onSuccess = null, onError = null, onDone = null) {
		return ajax(url, 'POST', data, onSuccess, onError, onDone);
	}

	const rememberWidgetSession = function(token) {
		if (!token) {
			return;
		}
		widgetSessionToken = token;
		try {
			window.sessionStorage.setItem(widgetSessionStorageKey, token);
		} catch (e) { }
	}

	const flushWidgetSessionWaiters = function() {
		var waiters = widgetSessionWaiters || [];
		widgetSessionWaiters = null;
		for (var i = 0; i < waiters.length; i++) {
			waiters[i]();
		}
	}

	const clearWidgetSession = function() {
		widgetSessionToken = null;
		try {
			window.sessionStorage.removeItem(widgetSessionStorageKey);
		} catch (e) { }
	};

	const ensureTrafficSession = function(onReady) {
		if (widgetSessionToken) {
			onReady();
			return;
		}
		if (widgetSessionWaiters) {
			widgetSessionWaiters.push(onReady);
			return;
		}
		widgetSessionWaiters = [onReady];
		ajaxPost(apiUrl + "/api/traffic/session", { keyToken: traffic_key }, function(result) {
			rememberWidgetSession(result && (result.sessionToken || result.SessionToken));
			flushWidgetSessionWaiters();
		}, function() {
			flushWidgetSessionWaiters();
		});
	}

	// ========================================
	// HELPER FUNCTIONS FOR TIMER OPERATIONS
	// ========================================

	/**
	 * Update button display with countdown
	 */
	const updateButtonDisplay = (show_code_button, element, timeInSeconds) => {
		const shown = clampRemainSeconds(timeInSeconds);
		if (element.dataset.click === 'true') {
			show_code_button.innerHTML = get_code_after_string + ' ' + shown;
			element.innerHTML = '';
			element.appendChild(show_code_button);
		}
		element.dataset.time = shown;
	};

	const createSolution1Timer = (show_code_button, element) => {
		var timeInMs = 1000 * traffic_wait_time;
		window.localStorage.setItem(cache_time, timeInMs);
		startWaitTicker({
			state: createWaitState(timeInMs),
			button: show_code_button,
			element: element,
			onComplete: function(timeInMs, timeInSeconds, prevMs) {
				var targetTime = parseRemainMs(window.localStorage.getItem(cache_time)) - 1000 * timeSangManHinhNew;
				if (reachedWaitMark(timeInMs, targetTime, prevMs)) {
					window.localStorage.setItem(cache_time, targetTime);
					checkClickManHinh(show_code_button, element);
					return true;
				}
				return false;
			},
			onZero: function() { checkButtonClick(); }
		});
	};
	const createFinalSolution1Timer = (show_code_button, element) => {
		var timeInMs = parseRemainMs(window.localStorage.getItem(cache_time));
		startWaitTicker({
			state: createWaitState(timeInMs),
			button: show_code_button,
			element: element,
			ignoreBlur: true,
			onTick: function(remainMs, timeInSeconds) {
				updateTrackingMessage('Tiếp tục lấy mã sau:');
				updateCounterMessage(timeInSeconds);
			},
			onZero: function() { checkButtonClick(); }
		});
	};

	const createSolution3Timer = (show_code_button, element, step) => {
		var timeInMs = 1000 * traffic_wait_time;
		window.localStorage.setItem(cache_time, timeInMs);
		startWaitTicker({
			state: createWaitState(timeInMs),
			button: show_code_button,
			element: element,
			onComplete: function(timeInMs, timeInSeconds, prevMs) {
				var targetTime = parseRemainMs(window.localStorage.getItem(cache_time)) - 1000 * timeSangManHinh;
				if (reachedWaitMark(timeInMs, targetTime, prevMs)) {
					window.localStorage.setItem(cache_time, targetTime);
					if (step >= 4) {
						checkScrollFinalSolution3(show_code_button, element);
					} else {
						checkClickManHinhSolution3(show_code_button, element, step);
					}
					return true;
				}
				return false;
			},
			onZero: function() { checkButtonClick(step); }
		});
	};
	const checkScrollFinalSolution3 = (show_code_button, element) => {

		showTrackingMessage('');
		updateCounterMessage('');
		updateTrackingMessage(requiredScrollUp);
		updateCounterMessage(window.localStorage.getItem(cache_time)/1e3);

		let typeScr = 'any';
		let previousScrollPosition = window.pageYOffset || document.documentElement.scrollTop;
		const detectScrollType = () => {
			let type = '';

			let scrollPosition = window.pageYOffset || document.documentElement.scrollTop;
			if (scrollPosition > previousScrollPosition) {
				type = 'scrollDown';
			} else if (scrollPosition < previousScrollPosition) {
				type = 'scrollUp';
			}
			previousScrollPosition = scrollPosition;

			return type;
		};

		const scrollHandler = (event) => {
			const scrollType = detectScrollType();
			if (scrollType === 'scrollUp' && (document.documentElement.scrollTop <= 0 || window.pageYOffset <= 0)) {
				window.removeEventListener('scroll', scrollHandler);
				var n = window.localStorage.getItem(cache_time);
				updateTrackingMessage('Tiếp tục lấy mã sau:');
				createFinalSolution1Timer(show_code_button, element);
			}
		}
		window.addEventListener('scroll', scrollHandler);

	}
	/**
	 * Create timer for solution 5 countdown
	 */
	const createSolution5Timer = (show_code_button, element, step) => {
		var timeInMs = 1000 * traffic_wait_time;
		window.localStorage.setItem(cache_time, timeInMs);
		startWaitTicker({
			state: createWaitState(timeInMs),
			button: show_code_button,
			element: element,
			onComplete: function(timeInMs, timeInSeconds, prevMs) {
				var targetTime = parseRemainMs(window.localStorage.getItem(cache_time)) - 1000 * timeSangManHinh;
				if (reachedWaitMark(timeInMs, targetTime, prevMs)) {
					window.localStorage.setItem(cache_time, targetTime);
					checkClickManHinhSolution5(show_code_button, element, step, "scrollUp");
					return true;
				}
				return false;
			},
			onZero: function() { checkButtonClick(step); }
		});
	};
	const checkScrollFinalSolution5 = (show_code_button, element) => {

		showTrackingMessage('');
		updateCounterMessage('');
		updateTrackingMessage(requiredScrollUp);
		updateCounterMessage(window.localStorage.getItem(cache_time)/1e3);

		let typeScr = 'any';
		let previousScrollPosition = window.pageYOffset || document.documentElement.scrollTop;
		const detectScrollType = () => {
			let type = '';

			let scrollPosition = window.pageYOffset || document.documentElement.scrollTop;
			if (scrollPosition > previousScrollPosition) {
				type = 'scrollDown';
			} else if (scrollPosition < previousScrollPosition) {
				type = 'scrollUp';
			}
			previousScrollPosition = scrollPosition;

			return type;
		};

		const scrollHandler = (event) => {
			const scrollType = detectScrollType();
			if (scrollType === 'scrollUp' && (document.documentElement.scrollTop <= 0 || window.pageYOffset <= 0)) {
				window.removeEventListener('scroll', scrollHandler);
				var n = window.localStorage.getItem(cache_time);
				updateTrackingMessage('Tiếp tục lấy mã sau:');
				createFinalSolution1Timer(show_code_button, element);
			}
		}
		window.addEventListener('scroll', scrollHandler);

	}
	function checkClickManHinhSolution5(show_code_button,element,step,typeCheck='',scrollDirection = ''){
		var clickHandler = ('ontouchstart' in document.documentElement ? "touchstart" : "click");
		updateTrackingMessage('Chạm vào màn hình để lấy mã');
		updateCounterMessage(window.localStorage.getItem(cache_time)/1e3);
		const clickManHinh1 = () =>{
			window.removeEventListener(clickHandler, clickManHinh1);
			var n = window.localStorage.getItem(cache_time);
			if(step != 3){

				checkScrollUpDownS5(show_code_button,element,step,typeCheck,scrollDirection);
			}
			else{
				updateTrackingMessage('Tiếp tục lấy mã sau:');
				createSolution5ClickScreenTimer(show_code_button, element, step);
			}
		}
		window.addEventListener(clickHandler, clickManHinh1);
	}
	const createSolution5ClickScreenTimer = (show_code_button, element, step) => {
		var timeInMs = parseRemainMs(window.localStorage.getItem(cache_time));
		updateTrackingMessage('Tiếp tục lấy mã sau:');
		startWaitTicker({
			state: createWaitState(timeInMs),
			button: show_code_button,
			element: element,
			onTick: function(remainMs, timeInSeconds) {
				updateCounterMessage(timeInSeconds);
			},
			onComplete: function(timeInMs, timeInSeconds, prevMs) {
				if (step == 3) {
					var targetTime = parseRemainMs(window.localStorage.getItem(cache_time)) - 1000 * timeSangManHinh;
					if (reachedWaitMark(timeInMs, targetTime, prevMs)) {
						window.localStorage.setItem(cache_time, targetTime);
						checkClickManHinhSolution5(show_code_button, element, step);
						return true;
					}
				}
				return false;
			},
			onZero: function() { checkButtonClick(step); }
		});
	};
	function checkScrollUpDownS5(show_code_button,element,step,typeCheck,scrollDirection=''){
		showTrackingMessage('');
		updateCounterMessage('');
		if(typeCheck === 'scrollUp'){
			updateTrackingMessage(requiredScrollUp);
			updateCounterMessage(window.localStorage.getItem(cache_time)/1e3);
		}
		if(typeCheck === 'scrollDown'){
			updateTrackingMessage(requiredScrollDown);
			updateCounterMessage(window.localStorage.getItem(cache_time)/1e3);
		}

		let typeScr = 'any';
		let previousScrollPosition = window.pageYOffset || document.documentElement.scrollTop;
		const detectScrollType = () => {
			let type = '';

			let scrollPosition = window.pageYOffset || document.documentElement.scrollTop;
			if (scrollPosition > previousScrollPosition) {
				type = 'scrollDown';
			} else if (scrollPosition < previousScrollPosition) {
				type = 'scrollUp';
			}
			previousScrollPosition = scrollPosition;

			return type;
		};

		const scrollHandler = (event) => {
			const scrollType = detectScrollType();
			if (scrollType === 'scrollUp' && typeCheck === 'scrollUp' && (document.documentElement.scrollTop <= 0 || window.pageYOffset <= 0)) {
				window.removeEventListener('scroll', scrollHandler);
				var n = window.localStorage.getItem(cache_time);
				updateTrackingMessage('Tiếp tục lấy mã sau:');
				if (scrollDirection != 'up') {
					createScrollTimerS5(show_code_button, element,step, 'scrollDown','down');
				}
				else{
					createFinalSolution1Timer(show_code_button, element);
				}

			}
			if (scrollType === 'scrollDown' && typeCheck === 'scrollDown' && ((window.innerHeight + window.pageYOffset + 2) >= document.body.offsetHeight)) {
				window.removeEventListener('scroll', scrollHandler);
				var n = window.localStorage.getItem(cache_time);
				updateTrackingMessage('Tiếp tục lấy mã sau:');
				if(step ==2){
					createSolution5ClickScreenTimer(show_code_button, element,step);
				}
				if(step ==4){
					createScrollTimerS5(show_code_button, element,step, 'scrollUp','up');
				}
			}
		}
		window.addEventListener('scroll', scrollHandler);
	}
	const createScrollTimerS5 = (show_code_button, element,step,typeCheck, scrollDirection='') => {
		var timeInMs = parseRemainMs(window.localStorage.getItem(cache_time));
		updateTrackingMessage('Tiếp tục lấy mã sau:');
		startWaitTicker({
			state: createWaitState(timeInMs),
			button: show_code_button,
			element: element,
			onTick: function(remainMs, timeInSeconds) {
				updateCounterMessage(timeInSeconds);
			},
			onComplete: function(timeInMs, timeInSeconds, prevMs) {
				var targetTime = parseRemainMs(window.localStorage.getItem(cache_time)) - 1000 * timeSangManHinh;
				if (step == 4 && scrollDirection != '') {
					targetTime = parseRemainMs(window.localStorage.getItem(cache_time)) - 1000 * 30;
				}
				if (reachedWaitMark(timeInMs, targetTime, prevMs)) {
					window.localStorage.setItem(cache_time, targetTime);
					if (scrollDirection != 'up') {
						checkClickManHinhSolution5(show_code_button, element, step, typeCheck, scrollDirection);
					} else {
						checkScrollUpDownS5(show_code_button, element, step, typeCheck, scrollDirection);
					}
					return true;
				}
				return false;
			},
			onZero: function() { checkButtonClick(step); }
		});
	};
	/**
	 * Create timer for solution 2 new countdown
	 */
	const createSolution2Timer = (show_code_button, element, step) => {
		var timeInMs = 1000 * traffic_wait_time;
		window.localStorage.setItem(cache_time, timeInMs);
		startWaitTicker({
			state: createWaitState(timeInMs),
			button: show_code_button,
			element: element,
			onComplete: function(timeInMs, timeInSeconds, prevMs) {
				var targetTime = parseRemainMs(window.localStorage.getItem(cache_time)) - 1000 * timeSangManHinh;
				if (reachedWaitMark(timeInMs, targetTime, prevMs)) {
					window.localStorage.setItem(cache_time, targetTime);
					checkClickManHinhSolution2(show_code_button, element, step);
					return true;
				}
				return false;
			},
			onZero: function() { checkButtonClickSolution2(step); }
		});
	};

	/**
	 * Create timer for scroll countdown
	 */
	const createScrollTimer = (show_code_button, element, scrollDirection) => {
		var timeInMs = parseRemainMs(window.localStorage.getItem(cache_time));
		updateTrackingMessage('Tiếp tục lấy mã sau:');
		startWaitTicker({
			state: createWaitState(timeInMs),
			button: show_code_button,
			element: element,
			onTick: function(remainMs, timeInSeconds) {
				updateCounterMessage(timeInSeconds);
			},
			onComplete: function(timeInMs, timeInSeconds, prevMs) {
				var targetTime = parseRemainMs(window.localStorage.getItem(cache_time)) - 1000 * timeSangManHinhNew;
				if (reachedWaitMark(timeInMs, targetTime, prevMs)) {
					window.localStorage.setItem(cache_time, targetTime);
					checkClickManHinh(show_code_button, element, scrollDirection);
					return true;
				}
				return false;
			},
			onZero: function() { checkButtonClick(); }
		});
	};

	/**
	 * Create timer for click screen countdown
	 */
	const createClickScreenTimer = (show_code_button, element, scroll = '') => {
		var timeInMs = parseRemainMs(window.localStorage.getItem(cache_time));
		updateTrackingMessage('Tiếp tục lấy mã sau:');

		var timeCheckScroll = timeToScrollUp;
		var typeScroll = 'scrollUp';

		if (scroll === 'down') {
			timeCheckScroll = timeToScrollDown;
			typeScroll = 'scrollDown';
		}

		startWaitTicker({
			state: createWaitState(timeInMs),
			button: show_code_button,
			element: element,
			onTick: function(remainMs, timeInSeconds) {
				updateCounterMessage(timeInSeconds);
			},
			onComplete: function(timeInMs, timeInSeconds, prevMs) {
				if (reachedWaitMark(timeInMs, 1000 * timeCheckScroll, prevMs)) {
					window.localStorage.setItem(cache_time, 1000 * timeCheckScroll);
					checkScrollUpDown(show_code_button, element, typeScroll);
					return true;
				}
				var targetTime = parseRemainMs(window.localStorage.getItem(cache_time)) - 1000 * timeSangManHinhNew;
				if (reachedWaitMark(timeInMs, targetTime, prevMs)) {
					window.localStorage.setItem(cache_time, targetTime);
					checkClickManHinh(show_code_button, element, scroll);
					return true;
				}
				return false;
			},
			onZero: function() { checkButtonClick(); }
		});
	};

	/**
	 * Create timer for solution 3 click screen countdown
	 */
	const createSolution3ClickScreenTimer = (show_code_button, element, step) => {
		var timeInMs = parseRemainMs(window.localStorage.getItem(cache_time));
		updateTrackingMessage('Tiếp tục lấy mã sau:');
		startWaitTicker({
			state: createWaitState(timeInMs),
			button: show_code_button,
			element: element,
			onTick: function(remainMs, timeInSeconds) {
				updateCounterMessage(timeInSeconds);
			},
			onZero: function() { checkButtonClick(step); }
		});
	};
	/**
	 * Create timer for solution 2 click screen countdown
	 */
	const createSolution2ClickScreenTimer = (show_code_button, element, step) => {
		var timeInMs = parseRemainMs(window.localStorage.getItem(cache_time));
		updateTrackingMessage('Tiếp tục lấy mã sau:');
		startWaitTicker({
			state: createWaitState(timeInMs),
			button: show_code_button,
			element: element,
			onTick: function(remainMs, timeInSeconds) {
				updateCounterMessage(timeInSeconds);
			},
			onComplete: function(timeInMs, timeInSeconds, prevMs) {
				if (step >= 3) {
					var targetTimeScroll = parseRemainMs(window.localStorage.getItem(cache_time)) - 5000;
					if (reachedWaitMark(timeInMs, targetTimeScroll, prevMs)) {
						window.localStorage.setItem(cache_time, targetTimeScroll);
						checkScrollFinalSolution3(show_code_button, element);
						return true;
					}
				}
				return false;
			},
			onZero: function() { checkButtonClickSolution2(step); }
		});
	};

	/**
	 * Create timer for solution 1 countdown
	 */
	const createSolution4Timer = (show_code_button, element) => {
		var timeInMs = 1000 * traffic_wait_time;
		window.localStorage.setItem(cache_time, timeInMs);
		startWaitTicker({
			state: createWaitState(timeInMs),
			button: show_code_button,
			element: element,
			onComplete: function(timeInMs, timeInSeconds, prevMs) {
				var targetTime = parseRemainMs(window.localStorage.getItem(cache_time)) - 1000 * timeSangManHinhS4;
				if (reachedWaitMark(timeInMs, targetTime, prevMs)) {
					window.localStorage.setItem(cache_time, targetTime);
					checkClickManHinhS4(show_code_button, element);
					return true;
				}
				return false;
			},
			onZero: function() { checkButtonClick(); }
		});
	};
	function checkClickManHinhS4(show_code_button,element,scroll=''){
		var clickHandler = ('ontouchstart' in document.documentElement ? "touchstart" : "click");
		updateTrackingMessage('Chạm vào màn hình để lấy mã');
		updateCounterMessage(window.localStorage.getItem(cache_time)/1e3);
		const clickManHinh = () =>{
			window.removeEventListener(clickHandler, clickManHinh);
			var n = window.localStorage.getItem(cache_time);
			updateTrackingMessage('Tiếp tục lấy mã sau:');
			createClickScreenTimerS4(show_code_button, element, scroll);
		}
		window.addEventListener(clickHandler, clickManHinh);

	}
	const createClickScreenTimerS4 = (show_code_button, element, scroll = '') => {
		var timeInMs = parseRemainMs(window.localStorage.getItem(cache_time));
		updateTrackingMessage('Tiếp tục lấy mã sau:');

		var timeCheckScroll = timeToScrollUpS4;
		var typeScroll = 'scrollUp';
		timeSangNewS4 = 15;

		if (scroll === 'down') {
			timeCheckScroll = timeToScrollDownS4;
			timeSangNewS4 = 20;
			typeScroll = 'scrollDown';
		}
		if (scroll === 'up') {
			timeCheckScroll = timeToScrollUpS4_2;
			timeSangNewS4 = 10;
			typeScroll = 'scrollUp';
		}

		startWaitTicker({
			state: createWaitState(timeInMs),
			button: show_code_button,
			element: element,
			onTick: function(remainMs, timeInSeconds) {
				updateCounterMessage(timeInSeconds);
			},
			onComplete: function(timeInMs, timeInSeconds, prevMs) {
				if (reachedWaitMark(timeInMs, 1000 * timeCheckScroll, prevMs)) {
					window.localStorage.setItem(cache_time, 1000 * timeCheckScroll);
					checkScrollUpDownS4(show_code_button, element, typeScroll);
					return true;
				}
				var targetTime = parseRemainMs(window.localStorage.getItem(cache_time)) - 1000 * timeSangNewS4;
				if (reachedWaitMark(timeInMs, targetTime, prevMs)) {
					window.localStorage.setItem(cache_time, targetTime);
					checkClickManHinhS4(show_code_button, element, scroll);
					return true;
				}
				return false;
			},
			onZero: function() { checkButtonClick(); }
		});
	};
	function checkScrollUpDownS4(show_code_button,element,typeCheck){
		showTrackingMessage('');
		updateCounterMessage('');
		if(typeCheck === 'scrollUp'){
			updateTrackingMessage(requiredScrollUp);
			updateCounterMessage(window.localStorage.getItem(cache_time)/1e3);
		}
		if(typeCheck === 'scrollDown'){
			updateTrackingMessage(requiredScrollDown);
			updateCounterMessage(window.localStorage.getItem(cache_time)/1e3);
		}

		let typeScr = 'any';
		let previousScrollPosition = window.pageYOffset || document.documentElement.scrollTop;
		const detectScrollType = () => {
			let type = '';

			let scrollPosition = window.pageYOffset || document.documentElement.scrollTop;
			if (scrollPosition > previousScrollPosition) {
				type = 'scrollDown';
			} else if (scrollPosition < previousScrollPosition) {
				type = 'scrollUp';
			}
			previousScrollPosition = scrollPosition;

			return type;
		};

		const scrollHandler = (event) => {
			const scrollType = detectScrollType();
			if (scrollType === 'scrollUp' && typeCheck === 'scrollUp' && (document.documentElement.scrollTop <= 0 || window.pageYOffset <= 0)) {
				window.removeEventListener('scroll', scrollHandler);
				var n = window.localStorage.getItem(cache_time);
				updateTrackingMessage('Tiếp tục lấy mã sau:');
				createScrollTimerS4(show_code_button, element, 'down');
			}
			if (scrollType === 'scrollDown' && typeCheck === 'scrollDown' && ((window.innerHeight + window.pageYOffset + 2) >= document.body.offsetHeight)) {
				window.removeEventListener('scroll', scrollHandler);
				var n = window.localStorage.getItem(cache_time);
				updateTrackingMessage('Tiếp tục lấy mã sau:');
				createScrollTimerS4(show_code_button, element, 'up');

			}
		}
		window.addEventListener('scroll', scrollHandler);
	}
	const createScrollTimerS4 = (show_code_button, element, scrollDirection) => {
		var timeInMs = parseRemainMs(window.localStorage.getItem(cache_time));
		updateTrackingMessage('Tiếp tục lấy mã sau:');
		startWaitTicker({
			state: createWaitState(timeInMs),
			button: show_code_button,
			element: element,
			onTick: function(remainMs, timeInSeconds) {
				updateCounterMessage(timeInSeconds);
			},
			onComplete: function(timeInMs, timeInSeconds, prevMs) {
				var targetTime = parseRemainMs(window.localStorage.getItem(cache_time)) - 1000 * timeSangNewS4;
				if (reachedWaitMark(timeInMs, targetTime, prevMs)) {
					window.localStorage.setItem(cache_time, targetTime);
					checkClickManHinhS4(show_code_button, element, scrollDirection);
					return true;
				}
				return false;
			},
			onZero: function() { checkButtonClick(); }
		});
	};

	const getVisitorInfo = function() {
		var unknown = "-";
		var screenSize = "";
		if (screen.width) {
			width = screen.width ? screen.width : "";
			height = screen.height ? screen.height : "";
			screenSize += "" + width + " x " + height;
		}
		var nVer = navigator.appVersion;
		var nAgt = navigator.userAgent;
		var browser = navigator.appName;
		var version = "" + parseFloat(navigator.appVersion);
		var majorVersion = parseInt(navigator.appVersion, 10);
		var nameOffset, verOffset, ix;
		if ((verOffset = nAgt.indexOf("Opera")) != -1) {
			browser = "Opera";
			version = nAgt.substring(verOffset + 6);
			if ((verOffset = nAgt.indexOf("Version")) != -1) {
				version = nAgt.substring(verOffset + 8);
			}
		}
		if ((verOffset = nAgt.indexOf("OPR")) != -1) {
			browser = "Opera";
			version = nAgt.substring(verOffset + 4);
		} else if ((verOffset = nAgt.indexOf("MSIE")) != -1) {
			browser = "Microsoft Internet Explorer";
			version = nAgt.substring(verOffset + 5);
		} else if ((verOffset = nAgt.indexOf("Chrome")) != -1) {
			browser = "Chrome";
			version = nAgt.substring(verOffset + 7);
		} else if ((verOffset = nAgt.indexOf("Safari")) != -1) {
			browser = "Safari";
			version = nAgt.substring(verOffset + 7);
			if ((verOffset = nAgt.indexOf("Version")) != -1) {
				version = nAgt.substring(verOffset + 8);
			}
		} else if ((verOffset = nAgt.indexOf("Firefox")) != -1) {
			browser = "Firefox";
			version = nAgt.substring(verOffset + 8);
		} else if (nAgt.indexOf("Trident/") != -1) {
			browser = "Microsoft Internet Explorer";
			version = nAgt.substring(nAgt.indexOf("rv:") + 3);
		} else if (
			(nameOffset = nAgt.lastIndexOf(" ") + 1) <
			(verOffset = nAgt.lastIndexOf("/"))
		) {
			browser = nAgt.substring(nameOffset, verOffset);
			version = nAgt.substring(verOffset + 1);
			if (browser.toLowerCase() == browser.toUpperCase()) {
				browser = navigator.appName;
			}
		}
		if ((ix = version.indexOf(";")) != -1) version = version.substring(0, ix);
		if ((ix = version.indexOf(" ")) != -1) version = version.substring(0, ix);
		if ((ix = version.indexOf(")")) != -1) version = version.substring(0, ix);
		majorVersion = parseInt("" + version, 10);
		if (isNaN(majorVersion)) {
			version = "" + parseFloat(navigator.appVersion);
			majorVersion = parseInt(navigator.appVersion, 10);
		}
		var mobile = /Mobile|mini|Fennec|Android|iP(ad|od|hone)/.test(nVer);
		var cookieEnabled = navigator.cookieEnabled ? true : false;
		if (typeof navigator.cookieEnabled == "undefined" && !cookieEnabled) {
			document.cookie = "testcookie";
			cookieEnabled =
				document.cookie.indexOf("testcookie") != -1 ? true : false;
		}
		var os = unknown;
		var clientStrings = [{
				s: "Windows 10",
				r: /(Windows 10.0|Windows NT 10.0)/
			},
			{
				s: "Windows 8.1",
				r: /(Windows 8.1|Windows NT 6.3)/
			},
			{
				s: "Windows 8",
				r: /(Windows 8|Windows NT 6.2)/
			},
			{
				s: "Windows 7",
				r: /(Windows 7|Windows NT 6.1)/
			},
			{
				s: "Windows Vista",
				r: /Windows NT 6.0/
			},
			{
				s: "Windows Server 2003",
				r: /Windows NT 5.2/
			},
			{
				s: "Windows XP",
				r: /(Windows NT 5.1|Windows XP)/
			},
			{
				s: "Windows 2000",
				r: /(Windows NT 5.0|Windows 2000)/
			},
			{
				s: "Windows ME",
				r: /(Win 9x 4.90|Windows ME)/
			},
			{
				s: "Windows 98",
				r: /(Windows 98|Win98)/
			},
			{
				s: "Windows 95",
				r: /(Windows 95|Win95|Windows_95)/
			},
			{
				s: "Windows NT 4.0",
				r: /(Windows NT 4.0|WinNT4.0|WinNT|Windows NT)/
			},
			{
				s: "Windows CE",
				r: /Windows CE/
			},
			{
				s: "Windows 3.11",
				r: /Win16/
			},
			{
				s: "Android",
				r: /Android/
			},
			{
				s: "Open BSD",
				r: /OpenBSD/
			},
			{
				s: "Sun OS",
				r: /SunOS/
			},
			{
				s: "Linux",
				r: /(Linux|X11)/
			},
			{
				s: "iOS",
				r: /(iPhone|iPad|iPod)/
			},
			{
				s: "Mac OS X",
				r: /Mac OS X/
			},
			{
				s: "Mac OS",
				r: /(MacPPC|MacIntel|Mac_PowerPC|Macintosh)/
			},
			{
				s: "QNX",
				r: /QNX/
			},
			{
				s: "UNIX",
				r: /UNIX/
			},
			{
				s: "BeOS",
				r: /BeOS/
			},
			{
				s: "OS/2",
				r: /OS\/2/
			},
			{
				s: "Search Bot",
				r: /(nuhk|Googlebot|Yammybot|Openbot|Slurp|MSNBot|Ask Jeeves\/Teoma|ia_archiver)/,
			},
		];
		for (var id in clientStrings) {
			var cs = clientStrings[id];
			if (cs.r.test(nAgt)) {
				os = cs.s;
				break;
			}
		}
		var osVersion = unknown;
		if (/Windows/.test(os)) {
			osVersion = /Windows (.*)/.exec(os)[1];
			os = "Windows";
		}
		switch (os) {
			case "Mac OS X":
				osVersion = /Mac OS X (10[\.\_\d]+)/.exec(nAgt)[1];
				break;
			case "Android":
				osVersion = /Android ([\.\_\d]+)/.exec(nAgt)[1];
				break;
			case "iOS":
				osVersion = /OS (\d+)_(\d+)_?(\d+)?/.exec(nVer);
				osVersion =
					osVersion[1] + "." + osVersion[2] + "." + (osVersion[3] | 0);
				break;
		}
		if (typeof swfobject != "undefined") {
			var fv = swfobject.getFlashPlayerVersion();
			if (fv.major > 0) {
				flashVersion = fv.major + "." + fv.minor + " r" + fv.release;
			} else {
				flashVersion = unknown;
			}
		}

		return {
			uuid: getVisitorUUID(),
			browser: browser,
			browserVersion: version,
			browserMajorVersion: majorVersion,
			cookies: cookieEnabled,
			mobile: mobile,
			os: os,
			osVersion: osVersion,
			screen: screenSize,
		};
	}
	const getVisitorUUID = function() {
		let uuid;

		try {
			uuid = localStorage.getItem("__"+traffic_key+"_uuid");
			if (uuid === null) {
				uuid = uuidv4();
				localStorage.setItem("__"+traffic_key+"_uuid", uuid);
			}
		} catch(e) {
			uuid = uuidv4();
		}

		return uuid;
	}
	const uuidv4 = function() {
		if (typeof crypto == 'object') {
			return uuidv4ByCrypto();
		}

		return uuidv4ByMath();
	}

	const uuidv4ByMath = function() {
		let d = new Date().getTime();//Timestamp
		let d2 = ((typeof performance !== 'undefined') && performance.now && (performance.now()*1000)) || 0;//Time in microseconds since page-load or 0 if unsupported
		return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
			let r = Math.random() * 16;//random number between 0 and 16
			if(d > 0){//Use timestamp until depleted
				r = (d + r)%16 | 0;
				d = Math.floor(d/16);
			} else {//Use microseconds since page-load if supported
				r = (d2 + r)%16 | 0;
				d2 = Math.floor(d2/16);
			}
			return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
		});
	}

	const uuidv4ByCrypto = function() {
		return ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g, function (c) {
			return (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16)
		});
	}
	const showTrackingMessage = (message,top = 45) => {
		if (trackingMessageContainer) {
			trackingMessageContainer.style[top] = top + '%';
			return
		}

		trackingMessageContainer = document.createElement('div')
		const trackingMessageContainerStyles = {
			backgroundColor: 'white',
			padding: '20px',
			fontWeight: 'bold',
			position: 'fixed',
			width: '400px',
			color: 'black',
			top: top +'%',
			left: 'calc(50% - 200px)',
			zIndex: 9999,
			borderRadius: '10px',
			textAlign: 'center',
			display: 'flex',
			justifyContent: 'center',
			flexDirection: 'column',
			alignItems: 'center',
			boxShadow: 'rgba(0, 0, 0, 0.16) 0px 10px 36px 0px, rgba(0, 0, 0, 0.06) 0px 0px 0px 1px',
		}

		for (const [key, value] of Object.entries(trackingMessageContainerStyles)) {
			trackingMessageContainer.style[key] = value
		}

		const messageElement = document.createElement('div')
		messageElement.setAttribute('id', 'message')
		const messageText = document.createTextNode(message)
		messageElement.appendChild(messageText)
		trackingMessageContainer.appendChild(messageElement)

		const counterElement = document.createElement('div')
		counterElement.setAttribute('id', 'counter')
		const counterStyles = {
			border: '1px solid lightgray',
			borderRadius: '999px',
			width: '45px',
			height: '45px',
			display: 'flex',
			justifyContent: 'center',
			alignItems: 'center',
		}

		for (const [key, value] of Object.entries(counterStyles)) {
			counterElement.style[key] = value
		}
		trackingMessageContainer.appendChild(counterElement)
		const xacthucButton = document.createElement('button');
		xacthucButton.setAttribute('id', 'xacthucButton')
		xacthucButton.textContent = 'Xác thực và lấy mã';
		xacthucButton.style.cssText = `
			background-color: #0bf405;
			color: white;
			border: none;
			padding: 12px 24px;
			border-radius: 5px;
			font-size: 14px;
			font-weight: bold;
			cursor: pointer;
			margin-top: 15px;
			width: 100%;
			display: none;
		`;
		xacthucButton.addEventListener('click', function() {
			var element = document.getElementById(traffic_key);
			var solution = window.localStorage.getItem(cache_solution);
			if (canOpenGetCode(element)) {
				showCaptchaModalForGetCode(element, solution);
			}
		});
		trackingMessageContainer.appendChild(xacthucButton)

		const retryButton = document.createElement('button');
		retryButton.setAttribute('id', 'getCodeRetryButton');
		retryButton.textContent = 'Thử lại';
		retryButton.style.cssText = `
			background-color: #0bf405;
			color: white;
			border: none;
			padding: 12px 24px;
			border-radius: 5px;
			font-size: 14px;
			font-weight: bold;
			cursor: pointer;
			margin-top: 15px;
			width: 100%;
			display: none;
		`;
		retryButton.addEventListener('click', function() {
			var element = document.getElementById(traffic_key);
			var solution = window.localStorage.getItem(cache_solution);
			if (canOpenGetCode(element)) {
				showCaptchaModalForGetCode(element, solution);
			}
		});
		trackingMessageContainer.appendChild(retryButton)

		document.body.appendChild(trackingMessageContainer);
	}
	const showElementToClickScreen = () => {
		if (elementToClickScreenContainer) {
			return
		}

		elementToClickScreenContainer = document.createElement('div')
		const elementToClickScreenContainerStyles = {
			backgroundColor: 'transparent',
			position: 'fixed',
			width: '100%',
			height: '100%',
			zIndex: 99999
		}

		for (const [key, value] of Object.entries(elementToClickScreenContainerStyles)) {
			elementToClickScreenContainer.style[key] = value
		}

		document.body.appendChild(elementToClickScreenContainer);
	}
	const updateCounterMessage = (counter) => {
		if (!trackingMessageContainer) {
			showTrackingMessage('')
		}

		const counterElement = trackingMessageContainer.querySelector('#counter')
		counterElement.innerHTML = '' + clampRemainSeconds(counter);
	}

	const updateTrackingMessage = (message,top = 45) => {
		if (!trackingMessageContainer) {
			showTrackingMessage(message,top)
		}

		const messageElement = trackingMessageContainer.querySelector('#message');
		trackingMessageContainer.style['top'] = top + '%';
		messageElement.innerHTML = message
	}
	// Captcha provider routing
	function getActiveCaptchaKind() {
		if (shouldUseQCaptcha() || captchaProvider === 'qcaptcha') {
			return 'qcaptcha';
		}
		if (captchaProvider === 'captchala') {
			return 'captchala';
		}
		return 'hcaptcha';
	}

	function showCaptchaModalForGetCode(element, solution) {
		if (!isGetCodeWaitSatisfied(element)) {
			return;
		}
		var kind = getActiveCaptchaKind();
		if (kind === 'qcaptcha') {
			showQCaptchaModalForGetCode(element, solution);
		} else if (kind === 'captchala') {
			showCaptchaLaModalForGetCode(element, solution);
		} else {
			showHCaptchaModalForGetCode(element, solution);
		}
	}

	function closeCaptchaModalOverlay(overlay, cleanup) {
		try {
			if (typeof cleanup === 'function') cleanup();
		} catch (e) {}
		if (overlay && overlay.parentNode) {
			overlay.parentNode.removeChild(overlay);
		}
	}

	function reloadCaptchaForGetCode(element, solution, overlay, cleanup, sameKindReload) {
		var kind = getActiveCaptchaKind();
		if (typeof sameKindReload === 'function' && sameKindReload(kind)) {
			return;
		}
		closeCaptchaModalOverlay(overlay, cleanup);
		showCaptchaModalForGetCode(element, solution);
	}

	function normalizeCaptchaHost(host) {
		if (!host) return '';
		var value = String(host).trim().toLowerCase();
		if (value.indexOf('://') >= 0) {
			try { value = new URL(value).hostname; } catch (e) {}
		}
		if (value.indexOf('/') >= 0) value = value.split('/')[0];
		if (value.indexOf(':') >= 0) value = value.split(':')[0];
		if (value.indexOf('www.') === 0) value = value.slice(4);
		return value;
	}

	function isQCaptchaDomain(host) {
		var current = normalizeCaptchaHost(host);
		if (!current || !qCaptchaDomains || !qCaptchaDomains.length) return false;
		for (var i = 0; i < qCaptchaDomains.length; i++) {
			var configured = normalizeCaptchaHost(qCaptchaDomains[i]);
			if (!configured) continue;
			if (current === configured || current.length > configured.length && current.slice(-(configured.length + 1)) === '.' + configured) {
				return true;
			}
		}
		return false;
	}

	function shouldUseQCaptcha() {
		return traffic_use_qcaptcha
			|| isQCaptchaDomain(window.location.hostname)
			|| isQCaptchaDomain(traffic_campain_domain);
	}

	function getQCaptchaApi() {
		return window.hcaptcha || window.qcaptcha;
	}

	function loadQCaptchaScript() {
		return new Promise((resolve, reject) => {
			if (getQCaptchaApi()) {
				resolve();
				return;
			}

			var base = qCaptchaScriptUrl;
			if (!base) {
				reject(new Error('QCaptcha script URL is not configured'));
				return;
			}
			var separator = base.indexOf('?') >= 0 ? '&' : '?';
			var script = document.createElement('script');
			script.src = base.indexOf('render=') >= 0 || base.indexOf('compat=') >= 0
				? base
				: (base + separator + 'render=explicit&compat=hcaptcha');
			script.async = true;
			script.defer = true;
			script.onload = function() {
				setTimeout(function() {
					if (getQCaptchaApi()) {
						resolve();
					} else {
						reject(new Error('QCaptcha failed to load'));
					}
				}, 200);
			};
			script.onerror = function() {
				reject(new Error('Failed to load QCaptcha script'));
			};
			document.head.appendChild(script);
		});
	}

	function fetchCaptchaNonce(onSuccess, onError) {
		var sessionToken = traffic_session_token || window.localStorage.getItem(cache_traffic_session);
		if (!sessionToken || !traffic_id) {
			if (onError) onError();
			return;
		}
		ajaxPost(
			apiUrl + "/api/traffic/captcha-nonce",
			{ trafficSessionToken: sessionToken, trafficId: traffic_id },
			function(result) {
				if (result && result.action) {
					onSuccess(result.action);
				} else if (onError) {
					onError();
				}
			},
			onError
		);
	}

	function showQCaptchaModalForGetCode(element, solution) {
		loadQCaptchaScript().then(function() {
			showQCaptchaModalInternal(element, solution);
		}).catch(function(error) {
			console.error('Failed to load QCaptcha:', error);
			alert('Không thể tải QCaptcha. Vui lòng thử lại.');
		});
	}

	function showQCaptchaModalInternal(element, solution) {
		var qCaptchaToken = null;
		var qCaptchaWidgetId = null;
		var api = getQCaptchaApi();
		if (!api || typeof api.render !== 'function') {
			alert('Không thể khởi tạo QCaptcha. Vui lòng thử lại.');
			return;
		}

		var modalOverlay = document.createElement('div');
		modalOverlay.id = 'qcaptcha-modal-overlay';
		modalOverlay.style.cssText = `
			position: fixed;
			top: 0;
			left: 0;
			width: 100%;
			height: 100%;
			background-color: rgba(0, 0, 0, 0.5);
			z-index: 9999;
			display: flex;
			justify-content: center;
			align-items: center;
		`;

		var modalContent = document.createElement('div');
		modalContent.id = 'qcaptcha-modal-content';
		modalContent.style.cssText = `
			background-color: white;
			padding: 30px;
			border-radius: 10px;
			box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
			max-width: 400px;
			width: 90%;
			text-align: center;
		`;

		var modalTitle = document.createElement('h3');
		modalTitle.textContent = 'Xác thực bảo mật.';
		modalTitle.style.cssText = `
			margin: 0 0 20px 0;
			color: #333;
			font-size: 18px;
			font-weight: bold;
		`;

		var qcaptchaContainer = document.createElement('div');
		qcaptchaContainer.className = 'h-captcha';
		qcaptchaContainer.setAttribute('data-sitekey', qCaptchaSiteKey);
		qcaptchaContainer.style.cssText = `
			display: flex;
			justify-content: center;
			margin: 20px 0;
			min-height: 78px;
		`;

		var reloadButton = document.createElement('button');
		reloadButton.textContent = 'Tải lại Captcha';
		reloadButton.type = 'button';
		reloadButton.style.cssText = `
			background-color: #007bff;
			color: white;
			border: none;
			padding: 8px 16px;
			border-radius: 5px;
			font-size: 12px;
			font-weight: bold;
			cursor: pointer;
			margin-top: 5px;
			width: 100%;
		`;

		var verifyButton = document.createElement('button');
		verifyButton.textContent = 'Xác thực và lấy mã';
		verifyButton.style.cssText = `
			background-color: #0bf405;
			color: white;
			border: none;
			padding: 12px 24px;
			border-radius: 5px;
			font-size: 14px;
			font-weight: bold;
			cursor: pointer;
			margin-top: 15px;
			width: 100%;
		`;

		var closeButton = document.createElement('button');
		closeButton.textContent = 'Đóng';
		closeButton.style.cssText = `
			background-color: #6c757d;
			color: white;
			border: none;
			padding: 8px 16px;
			border-radius: 5px;
			font-size: 12px;
			cursor: pointer;
			margin-top: 10px;
		`;

		var modalTitleNoti = document.createElement('h4');
		modalTitleNoti.textContent = 'Nếu Captcha không hiển thị, bấm "Tải lại Captcha". Nếu vẫn lỗi, bấm Đóng và thử lại.';
		modalTitleNoti.style.cssText = `
			margin: 0 0 20px 0;
			color: #333;
			font-size: 14px;
			font-weight: bold;
		`;

		function resetQCaptchaWidget() {
			qCaptchaToken = null;
			if (qCaptchaWidgetId != null && typeof api.reset === 'function') {
				try { api.reset(qCaptchaWidgetId); } catch (e) {}
			}
		}

		function renderQCaptchaWidget() {
			qCaptchaToken = null;
			qcaptchaContainer.innerHTML = '';
			fetchCaptchaNonce(function(action) {
				qcaptchaContainer.innerHTML = '';
				qcaptchaContainer.setAttribute('data-action', action);
				var params = {
					sitekey: qCaptchaSiteKey,
					action: action,
					callback: function(token) { qCaptchaToken = token; },
					'expired-callback': function() { qCaptchaToken = null; },
					'error-callback': function() { qCaptchaToken = null; }
				};
				qCaptchaWidgetId = api.render(qcaptchaContainer, params);
				qcaptchaContainer.dataset.widgetId = qCaptchaWidgetId;
			}, function() {
				alert('Không thể gắn phiên captcha. Vui lòng tải lại trang và thử lại.');
			});
		}

		reloadButton.addEventListener('click', function() {
			reloadCaptchaForGetCode(element, solution, modalOverlay, resetQCaptchaWidget, function(kind) {
				if (kind !== 'qcaptcha') return false;
				resetQCaptchaWidget();
				renderQCaptchaWidget();
				return true;
			});
		});

		verifyButton.addEventListener('click', function() {
			if (!qCaptchaToken && qCaptchaWidgetId != null && typeof api.getResponse === 'function') {
				try { qCaptchaToken = api.getResponse(qCaptchaWidgetId); } catch (e) {}
			}
			if (!qCaptchaToken) {
				alert('Vui lòng hoàn thành xác thực QCaptcha');
				return;
			}
			document.body.removeChild(modalOverlay);
			submitGetCodeRequest(element, solution, { qCaptchaToken: qCaptchaToken });
		});

		closeButton.addEventListener('click', function() {
			resetQCaptchaWidget();
			document.body.removeChild(modalOverlay);
		});

		modalOverlay.addEventListener('click', function(e) {
			if (e.target === modalOverlay) {
				resetQCaptchaWidget();
				document.body.removeChild(modalOverlay);
			}
		});

		modalContent.appendChild(modalTitle);
		modalContent.appendChild(qcaptchaContainer);
		modalContent.appendChild(reloadButton);
		modalContent.appendChild(verifyButton);
		modalContent.appendChild(closeButton);
		modalContent.appendChild(modalTitleNoti);
		modalOverlay.appendChild(modalContent);
		document.body.appendChild(modalOverlay);

		renderQCaptchaWidget();
	}

	// Load CaptchaLa script dynamically
	function loadCaptchaLaScript() {
		return new Promise((resolve, reject) => {
			if (window.loadCaptchala && typeof window.loadCaptchala === 'function') {
				window.loadCaptchala(function() {
					resolve();
				});
				return;
			}

			var script = document.createElement('script');
			script.src = 'https://cdn.captcha-cdn.net/captchala-loader.js';
			script.async = true;
			script.onload = function() {
				window.loadCaptchala(function() {
					resolve();
				});
			};
			script.onerror = function() {
				reject(new Error('Failed to load CaptchaLa script'));
			};
			document.head.appendChild(script);
		});
	}

	function extractGetCodeErrorMessage(payload) {
		var fallback = 'Lỗi khi lấy mã. Bạn vui lòng thử lại.';
		if (!payload) {
			return fallback;
		}
		var body = payload.response != null ? payload.response : payload;
		if (typeof body === 'string') {
			var trimmed = body.trim();
			if (!trimmed) {
				return fallback;
			}
			try {
				body = JSON.parse(trimmed);
			} catch (e) {
				return trimmed;
			}
		}
		if (!body || typeof body !== 'object') {
			return fallback;
		}
		return body.html || body.Html || body.message || body.Message || body.detail || body.Detail || fallback;
	}

	function setTrackingMessageColor(color) {
		if (!trackingMessageContainer) {
			return;
		}
		var messageElement = trackingMessageContainer.querySelector('#message');
		if (messageElement) {
			messageElement.style.color = color || '';
		}
	}

	function setTrackingCounterVisible(visible) {
		if (!trackingMessageContainer) {
			return;
		}
		var counterElement = trackingMessageContainer.querySelector('#counter');
		if (counterElement) {
			counterElement.style.display = visible ? 'flex' : 'none';
		}
	}

	function hideGetCodeActionButtons() {
		var xacthucButton = document.getElementById('xacthucButton');
		if (xacthucButton) {
			xacthucButton.style.display = 'none';
		}
		var retryButton = document.getElementById('getCodeRetryButton');
		if (retryButton) {
			retryButton.style.display = 'none';
		}
	}

	function showGetCodeLoading() {
		updateTrackingMessage('Đang lấy mã...');
		setTrackingMessageColor('');
		setTrackingCounterVisible(false);
		hideGetCodeActionButtons();
	}

	function showGetCodeError(message) {
		updateTrackingMessage(message || 'Lỗi khi lấy mã. Bạn vui lòng thử lại.');
		setTrackingMessageColor('#c62828');
		setTrackingCounterVisible(false);
		var xacthucButton = document.getElementById('xacthucButton');
		if (xacthucButton) {
			xacthucButton.style.display = 'none';
		}
		var retryButton = document.getElementById('getCodeRetryButton');
		if (retryButton) {
			retryButton.style.display = 'block';
		}
	}

	function submitGetCodeRequest(element, solution, captchaPayload, isRetry) {
		if (!isGetCodeWaitSatisfied(element)) {
			return;
		}
		element.dataset.loading = 'true';
		showGetCodeLoading();
		ensureTrafficSession(function() {
		ajaxPost(
			apiUrl + "/api/traffic/getcode",
			{
				...getVisitorInfo(),
				referrer: getReferrer(),
				trafficId: traffic_id,
				trafficSessionToken: traffic_session_token || window.localStorage.getItem(cache_traffic_session),
				solution: solution,
				...captchaPayload
			},
			(result) => {
				if(result && result.success){
					window.localStorage.removeItem(cache_flatform);
					window.localStorage.removeItem(cache_solution);
					window.localStorage.removeItem(count_step);
					window.localStorage.removeItem(cache_traffic_session);
					let radomTop = 45 + Math.floor(Math.random() * 35);
					setTrackingCounterVisible(false);
					setTrackingMessageColor('');
					hideGetCodeActionButtons();
					updateTrackingMessage(code_string + ': ' + result.html + '<img alt="' + window.location.hostname + '" src="https://' + traffic_domain + '/images/icons/icon-copy.png" style="height: 14px !important;margin: -5px 0 0 3px !important;vertical-align: middle;display: inline-block;width:auto !important;">',radomTop);
					trackingMessageContainer.addEventListener("click", function(){
						if(copyTextToClipboard(result.html)){
							var tooltip = createTooltip(copied_notify);
							trackingMessageContainer.appendChild(tooltip);
							window.setTimeout(function(){
								tooltip.remove();
							},3000);
						}
						return false;
					});
					element.dataset.loaded = true;
				}else{
					showGetCodeError(extractGetCodeErrorMessage(result));
				}
			},
			(event) => {
				if (!isRetry && event && event.status === 401) {
					element.dataset.retryingSession = 'true';
					clearWidgetSession();
					submitGetCodeRequest(element, solution, captchaPayload, true);
					return;
				}
				showGetCodeError(extractGetCodeErrorMessage(event));
			},
			() => {
				if (element.dataset.retryingSession === 'true') {
					delete element.dataset.retryingSession;
					return;
				}
				element.dataset.loading = 'false';
			}
		);
		});
	}

	// CaptchaLa Modal Functions
	function showCaptchaLaModalForGetCode(element, solution) {
		loadCaptchaLaScript().then(() => {
			showCaptchaLaModalInternal(element, solution);
		}).catch((error) => {
			console.error('Failed to load CaptchaLa:', error);
			alert('Không thể tải CaptchaLa. Vui lòng thử lại.');
		});
	}

	function showCaptchaLaModalInternal(element, solution) {
		var captchaLaToken = null;
		var captchaLaInstance = null;

		var modalOverlay = document.createElement('div');
		modalOverlay.id = 'captchala-modal-overlay';
		modalOverlay.style.cssText = `
			position: fixed;
			top: 0;
			left: 0;
			width: 100%;
			height: 100%;
			background-color: rgba(0, 0, 0, 0.5);
			z-index: 9999;
			display: flex;
			justify-content: center;
			align-items: center;
		`;

		var modalContent = document.createElement('div');
		modalContent.id = 'captchala-modal-content';
		modalContent.style.cssText = `
			background-color: white;
			padding: 30px;
			border-radius: 10px;
			box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
			max-width: 400px;
			width: 90%;
			text-align: center;
		`;

		var modalTitle = document.createElement('h3');
		modalTitle.textContent = 'Xác thực bảo mật.';
		modalTitle.style.cssText = `
			margin: 0 0 20px 0;
			color: #333;
			font-size: 18px;
			font-weight: bold;
		`;

		var captchaLaContainer = document.createElement('div');
		captchaLaContainer.style.cssText = `
			display: flex;
			justify-content: center;
			margin: 20px 0;
			min-height: 48px;
			width: 100%;
		`;

		var reloadButton = document.createElement('button');
		reloadButton.textContent = 'Tải lại Captcha';
		reloadButton.type = 'button';
		reloadButton.style.cssText = `
			background-color: #007bff;
			color: white;
			border: none;
			padding: 8px 16px;
			border-radius: 5px;
			font-size: 12px;
			font-weight: bold;
			cursor: pointer;
			margin-top: 5px;
			width: 100%;
		`;

		var verifyButton = document.createElement('button');
		verifyButton.textContent = 'Xác thực và lấy mã';
		verifyButton.style.cssText = `
			background-color: #0bf405;
			color: white;
			border: none;
			padding: 12px 24px;
			border-radius: 5px;
			font-size: 14px;
			font-weight: bold;
			cursor: pointer;
			margin-top: 15px;
			width: 100%;
		`;

		var closeButton = document.createElement('button');
		closeButton.textContent = 'Đóng';
		closeButton.style.cssText = `
			background-color: #6c757d;
			color: white;
			border: none;
			padding: 8px 16px;
			border-radius: 5px;
			font-size: 12px;
			cursor: pointer;
			margin-top: 10px;
		`;

		var modalTitleNoti = document.createElement('h4');
		modalTitleNoti.textContent = 'Nếu Captcha không hiển thị, bấm "Tải lại Captcha". Nếu vẫn lỗi, bấm Đóng và thử lại.';
		modalTitleNoti.style.cssText = `
			margin: 0 0 20px 0;
			color: #333;
			font-size: 14px;
			font-weight: bold;
		`;

		function destroyCaptchaLaInstance() {
			if (!captchaLaInstance) {
				return;
			}
			try {
				if (typeof captchaLaInstance.destroy === 'function') {
					captchaLaInstance.destroy();
				} else if (typeof captchaLaInstance.reset === 'function') {
					captchaLaInstance.reset();
				}
			} catch (error) {
				console.error('CaptchaLa destroy/reset error:', error);
			}
			captchaLaInstance = null;
		}

		function buildCaptchaLaInitOptions() {
			var options = {
				appKey: captchaLaAppKey,
				product: captchaLaProduct || 'float',
				action: captchaLaAction,
				lang: captchaLaLang,
				theme: { custom: { brightness: captchaLaTheme || 'light' } }
			};
			if (captchaLaForceType) {
				options.forceType = captchaLaForceType;
			}
			if (captchaLaDifficulty) {
				options.forceDifficulty = captchaLaDifficulty;
			}
			return options;
		}

		function initCaptchaLaWidget() {
			captchaLaToken = null;
			destroyCaptchaLaInstance();
			captchaLaContainer.innerHTML = '';
			captchaLaContainer.id = 'captchala-container-' + Date.now();

			captchaLaInstance = Captchala.init(buildCaptchaLaInitOptions())
			.appendTo('#' + captchaLaContainer.id)
			.onSuccess(function(res) {
				captchaLaToken = res.token;
			})
			.onError(function(err) {
				console.error('CaptchaLa error:', err.message);
			});
		}

		reloadButton.addEventListener('click', function() {
			reloadCaptchaForGetCode(element, solution, modalOverlay, destroyCaptchaLaInstance, function(kind) {
				if (kind !== 'captchala') return false;
				initCaptchaLaWidget();
				return true;
			});
		});

		verifyButton.addEventListener('click', function() {
			if (!captchaLaToken) {
				alert('Vui lòng hoàn thành xác thực CaptchaLa');
				return;
			}
			console.log("captchalaToken: " + captchaLaToken);
			destroyCaptchaLaInstance();
			document.body.removeChild(modalOverlay);
			submitGetCodeRequest(element, solution, { captchaLaToken: captchaLaToken });
		});

		closeButton.addEventListener('click', function() {
			destroyCaptchaLaInstance();
			document.body.removeChild(modalOverlay);
		});

		modalOverlay.addEventListener('click', function(e) {
			if (e.target === modalOverlay) {
				destroyCaptchaLaInstance();
				document.body.removeChild(modalOverlay);
			}
		});

		modalContent.appendChild(modalTitle);
		modalContent.appendChild(captchaLaContainer);
		modalContent.appendChild(reloadButton);
		modalContent.appendChild(verifyButton);
		modalContent.appendChild(closeButton);
		modalContent.appendChild(modalTitleNoti);
		modalOverlay.appendChild(modalContent);
		document.body.appendChild(modalOverlay);

		initCaptchaLaWidget();
	}

	// Load hCaptcha script dynamically
	function loadHCaptchaScript() {
		return new Promise((resolve, reject) => {
			// Check if hCaptcha is already loaded
			if (window.hcaptcha) {
				resolve();
				return;
			}

			// Create script element
			var script = document.createElement('script');
			script.src = 'https://js.hcaptcha.com/1/api.js?hl=vi&render=explicit';
			script.async = true;
			script.defer = true;

			// Handle script load
			script.onload = function() {
				// Wait a bit for hCaptcha to initialize
				setTimeout(() => {
					if (window.hcaptcha) {
						resolve();
					} else {
						reject(new Error('hCaptcha failed to load'));
					}
				}, 1000);
			};

			// Handle script error
			script.onerror = function() {
				reject(new Error('Failed to load hCaptcha script'));
			};

			// Add script to head
			document.head.appendChild(script);
		});
	}

	// hCaptcha Utility Functions
	function createHCaptchaWidget(container, siteKey) {
		if (!siteKey || siteKey.indexOf('your-hcaptcha') !== -1) {
			console.error('hCaptcha sitekey không hợp lệ:', siteKey);
			return null;
		}
		var widgetId = hcaptcha.render(container, {
			sitekey: siteKey,
			callback: function(token) {
				// Optional callback when user completes challenge
				console.log('hCaptcha completed with token:', token);
			}
		});

		// Store widget ID for later use
		container.dataset.widgetId = widgetId;
		return widgetId;
	}

	function getHCaptchaResponse(container) {
		var widgetId = container.dataset.widgetId;
		return widgetId ? hcaptcha.getResponse(widgetId) : null;
	}

	function resetHCaptchaWidget(container) {
		var widgetId = container.dataset.widgetId;
		if (widgetId) {
			hcaptcha.reset(widgetId);
		}
	}

	// hCaptcha Modal Functions
	function showHCaptchaModalForGetCode(element, solution) {
		
		// Load hCaptcha script first, then show modal
		loadHCaptchaScript().then(() => {
			showHCaptchaModalInternal(element, solution);
		}).catch((error) => {
			console.error('Failed to load hCaptcha:', error);
			alert('Không thể tải hCaptcha. Vui lòng thử lại.');
		});
		//showHCaptchaModalInternal(element, solution);
	}

	function showHCaptchaModalInternal(element, solution) {
		// Create modal overlay
		var modalOverlay = document.createElement('div');
		modalOverlay.id = 'hcaptcha-modal-overlay';
		modalOverlay.style.cssText = `
			position: fixed;
			top: 0;
			left: 0;
			width: 100%;
			height: 100%;
			background-color: rgba(0, 0, 0, 0.5);
			z-index: 9999;
			display: flex;
			justify-content: center;
			align-items: center;
		`;

		// Create modal content
		var modalContent = document.createElement('div');
		modalContent.id = 'hcaptcha-modal-content';
		modalContent.style.cssText = `
			background-color: white;
			padding: 30px;
			border-radius: 10px;
			box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
			max-width: 400px;
			width: 90%;
			text-align: center;
		`;

		// Create modal title
		var modalTitle = document.createElement('h3');
		modalTitle.textContent = 'Xác thực bảo mật.';
		modalTitle.style.cssText = `
			margin: 0 0 20px 0;
			color: #333;
			font-size: 18px;
			font-weight: bold;
		`;

		// Create hCaptcha container
		var hcaptchaContainer = document.createElement('div');
		hcaptchaContainer.className = 'h-captcha-widget';
		hcaptchaContainer.setAttribute('data-sitekey', hCaptchaSiteKey);
		hcaptchaContainer.style.cssText = `
			display: flex;
			justify-content: center;
			margin: 20px 0;
		`;

		// Create verify button
		var verifyButton = document.createElement('button');
		verifyButton.textContent = 'Xác thực và lấy mã';
		verifyButton.style.cssText = `
			background-color: #0bf405;
			color: white;
			border: none;
			padding: 12px 24px;
			border-radius: 5px;
			font-size: 14px;
			font-weight: bold;
			cursor: pointer;
			margin-top: 15px;
			width: 100%;
		`;

		// Create close button
		var closeButton = document.createElement('button');
		closeButton.textContent = 'Đóng';
		closeButton.style.cssText = `
			background-color: #6c757d;
			color: white;
			border: none;
			padding: 8px 16px;
			border-radius: 5px;
			font-size: 12px;
			cursor: pointer;
			margin-top: 10px;
		`;
		// Create modal title noti
		var modalTitleNoti = document.createElement('h4');
		modalTitleNoti.textContent = 'Nếu Captcha Lỗi, Bấm Đóng Và Xác Thực Captcha Lại';
		modalTitleNoti.style.cssText = `
			margin: 0 0 20px 0;
			color: #333;
			font-size: 14px;
			font-weight: bold;
		`;
		//const delay = (delayInms) => {
		  //return new Promise(resolve => setTimeout(resolve, delayInms));
		//};

		// Add event listeners
		verifyButton.addEventListener('click', function() {

			var hcaptchaToken = getHCaptchaResponse(hcaptchaContainer);
			if (!hcaptchaToken) {
				alert('Vui lòng hoàn thành xác thực hCaptcha');
				return;
			}
			console.log("hcaptchaToken: " + hcaptchaToken)
			// Close modal
			document.body.removeChild(modalOverlay);

			submitGetCodeRequest(element, solution, {
				hCaptchaToken: hcaptchaToken,
				hCaptchaTokenDuPhong: hCaptchaTokenDefault
			});
		});

		closeButton.addEventListener('click', function() {
			var widgetId = hcaptchaContainer.dataset.widgetId;
			if (widgetId) {
				hcaptcha.reset(widgetId);
			}
			document.body.removeChild(modalOverlay);
		});

		// Close modal when clicking overlay
		modalOverlay.addEventListener('click', function(e) {
			if (e.target === modalOverlay) {
				var widgetId = hcaptchaContainer.dataset.widgetId;
				if (widgetId) {
					hcaptcha.reset(widgetId);
				}
				document.body.removeChild(modalOverlay);
			}
		});

		// Assemble modal
		modalContent.appendChild(modalTitle);
		modalContent.appendChild(hcaptchaContainer);
		modalContent.appendChild(verifyButton);
		modalContent.appendChild(closeButton);
		modalContent.appendChild(modalTitleNoti);
		modalOverlay.appendChild(modalContent);

		// Add to page
		document.body.appendChild(modalOverlay);

		// Render hCaptcha
		createHCaptchaWidget(hcaptchaContainer, hCaptchaSiteKey);
	}

	function showHCaptchaModal(element, show_code_button, n) {
		// Load hCaptcha script first, then show modal
		//loadHCaptchaScript().then(() => {
			//showHCaptchaModalInternalOld(element, show_code_button, n);
		//}).catch((error) => {
			//console.error('Failed to load hCaptcha:', error);
			//alert('Không thể tải hCaptcha. Vui lòng thử lại.');
		//});
		showHCaptchaModalInternalOld(element, show_code_button, n);
	}

	function showHCaptchaModalInternalOld(element, show_code_button, n) {
		// Create modal overlay
		var modalOverlay = document.createElement('div');
		modalOverlay.id = 'hcaptcha-modal-overlay';
		modalOverlay.style.cssText = `
			position: fixed;
			top: 0;
			left: 0;
			width: 100%;
			height: 100%;
			background-color: rgba(0, 0, 0, 0.5);
			z-index: 9999;
			display: flex;
			justify-content: center;
			align-items: center;
		`;

		// Create modal content
		var modalContent = document.createElement('div');
		modalContent.id = 'hcaptcha-modal-content';
		modalContent.style.cssText = `
			background-color: white;
			padding: 30px;
			border-radius: 10px;
			box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
			max-width: 400px;
			width: 90%;
			text-align: center;
		`;

		// Create modal title
		var modalTitle = document.createElement('h3');
		modalTitle.textContent = 'Xác thực bảo mật';
		modalTitle.style.cssText = `
			margin: 0 0 20px 0;
			color: #333;
			font-size: 18px;
			font-weight: bold;
		`;

		// Create hCaptcha container
		var hcaptchaContainer = document.createElement('div');
		hcaptchaContainer.className = 'h-captcha-widget';
		hcaptchaContainer.setAttribute('data-sitekey', hCaptchaSiteKey);
		hcaptchaContainer.style.cssText = `
			display: flex;
			justify-content: center;
			margin: 20px 0;
		`;

		// Create verify button
		var verifyButton = document.createElement('button');
		verifyButton.textContent = 'Xác thực và lấy mã';
		verifyButton.style.cssText = `
			background-color: #0bf405;
			color: white;
			border: none;
			padding: 12px 24px;
			border-radius: 5px;
			font-size: 14px;
			font-weight: bold;
			cursor: pointer;
			margin-top: 15px;
			width: 100%;
		`;

		// Create close button
		var closeButton = document.createElement('button');
		closeButton.textContent = 'Đóng';
		closeButton.style.cssText = `
			background-color: #6c757d;
			color: white;
			border: none;
			padding: 8px 16px;
			border-radius: 5px;
			font-size: 12px;
			cursor: pointer;
			margin-top: 10px;
		`;

		// Add event listeners
		verifyButton.addEventListener('click', function() {
			var hcaptchaToken = getHCaptchaResponse(hcaptchaContainer);
			if (!hcaptchaToken) {

			}
			console.log(hcaptchaToken);

			// Close modal
			document.body.removeChild(modalOverlay);

			// Start the timer and process
			show_code_button.innerHTML = get_code_after_string + ' ' + n/1e3;
			element.innerHTML = '';
			element.appendChild(show_code_button);
			element.dataset.time = traffic_wait_time;
			element.dataset.click = 'true';
			element.dataset.hcaptchaToken = hcaptchaToken; // Store token for later use
			createSolution1Timer(show_code_button, element);
		});

		closeButton.addEventListener('click', function() {
			var widgetId = hcaptchaContainer.dataset.widgetId;
			if (widgetId) {
				hcaptcha.reset(widgetId);
			}
			document.body.removeChild(modalOverlay);
		});

		// Close modal when clicking overlay
		modalOverlay.addEventListener('click', function(e) {
			if (e.target === modalOverlay) {
				var widgetId = hcaptchaContainer.dataset.widgetId;
				if (widgetId) {
					hcaptcha.reset(widgetId);
				}
				document.body.removeChild(modalOverlay);
			}
		});

		// Assemble modal
		modalContent.appendChild(modalTitle);
		modalContent.appendChild(hcaptchaContainer);
		modalContent.appendChild(verifyButton);
		modalContent.appendChild(closeButton);
		modalOverlay.appendChild(modalContent);

		// Add to page
		document.body.appendChild(modalOverlay);

		// Render hCaptcha
		createHCaptchaWidget(hcaptchaContainer, hCaptchaSiteKey);
	}

	/******** Our traffic_main function ********/
	function traffic_main() {
		startSpeedHackWatch();
		ensureTrafficSession(function() {});

		var initScript = function(){
			if(loaded_script){
				return;
			}

			var randomSolution = window.localStorage.getItem(cache_solution);
			if (randomSolution === null || randomSolution == 0) {
				randomSolution = Math.floor((Math.random() * 2));
				//randomSolution = 4;
			}else{
				//check reference
				let refe = checkReferer(getReferrer());
				console.log("check solution refe = " + refe);
				if(refe != 'clicklink'){
					window.localStorage.removeItem(cache_flatform);
					window.localStorage.removeItem(cache_solution);
					window.localStorage.removeItem(count_step);
					window.localStorage.removeItem(cache_traffic_session);
					randomSolution = Math.floor((Math.random() * 2));
					//randomSolution = 4;
				}

			}
			const parts = window.location.hostname.split('.');
			const subdomain = parts.slice(0, -2).join('.');
			if (subdomain.includes("sunwin")) randomSolution = 0;
			window.localStorage.setItem(cache_solution,randomSolution);
			if (randomSolution == 0) {
				const referrer = getReferrer();
				var flatform = checkReferer(referrer);
				console.log("check solution 1 flatform = " + flatform);
				if(flatform != 'clicklink'){
					check_ref =true;
					ajaxGet(
						buildCampainUrl(flatform, 1, 1, false),
						(result) => {
							traffic_id = result.id;
							campaignTimeOnSite = Number(result.timeOnSitePerView) || 0;
							var element = document.getElementById(traffic_key);
							var numberPositionRandom = Math.floor(Math.random() * 9) + 4;
							var widthRan = Math.floor(numberPositionRandom *100 /12);
							var numberFloatRandom = Math.floor((Math.random() * 2));
							var styleFloat = numberFloatRandom == 0 ? 'left' : 'right';
							var styleRandom = document.createElement('style');
							styleRandom.type = 'text/css';
							styleRandom.innerHTML = '.colRan-' +  numberPositionRandom + ' { width:' + widthRan + '%;flex:0 0 auto;float:'+styleFloat+'}';
							document.getElementsByTagName('head')[0].appendChild(styleRandom);
							var numberAlignRandom = Math.floor(Math.random() * 3);
							var alignText = numberAlignRandom == 0 ? 'left !important' : (numberAlignRandom == 1 ? 'center !important' : 'right !important');
							var styleAlignRandom = document.createElement('style');
							styleAlignRandom.type = 'text/css';
							styleAlignRandom.innerHTML = '.alignRan' + ' { text-align:' + alignText + ';}';
							document.getElementsByTagName('head')[0].appendChild(styleAlignRandom);
							element.classList.add('colRan-' +  numberPositionRandom);
							element.classList.add('alignRan');

							//start solution 1: 1 trang, random 80–120s (không lấy timeOnSite)
							traffic_wait_time = randomIntInclusive(80, 120);
							alignWaitWithServer();
							timeSangManHinhNew = timeSangManHinhNew + Math.floor(Math.random() * 20);
							timeToScrollUp = traffic_wait_time - timeSangManHinhNew - 3;
							timeToScrollDown = timeToScrollUp - timeSangManHinhNew - 3;
							//timeToScrollUp2 = timeToScrollDown - (65 + Math.floor(Math.random() * 10));
							applyServerWaitSession(result, true);
							if(element
								&& check_ref
								&& get_code
							){
								//showElementToClickScreen();
								loaded_script = true;

								// element.style.background = '#fff';
								element.style.padding = '5px';
								element.style.color = '#000';
								element.style.position = 'relative';
								element.style.clear = 'both';


								var button = document.createElement("span");
								button.innerHTML = '<span style="display:inline-block;vertical-align:middle;color:#fff">' + get_code_string + '</span>';
								button.style.background = '#0bf405';
								button.style.border = '1px solid #fff';
								button.style.color = '#fff';
								button.style.fontWeight = '700';
								button.style.fontSize = '14px';
								button.style.borderRadius = '7px';
								button.style.padding = '5px 10px';
								button.style.margin = '5px';
								button.style.minHeight = 'auto';
								button.style.lineHeight = '20px';
								button.style.verticalAlign = 'middle';
								button.style.width = 'auto';
								button.style.cursor = 'pointer';
								button.style.display = 'inline-block';

								var show_code_button = document.createElement("div");
								show_code_button.innerHTML = '';
								show_code_button.style.background = '#0bf405';
								show_code_button.style.border = '1px solid #fff';
								show_code_button.style.color = '#fff';
								show_code_button.style.fontWeight = '700';
								show_code_button.style.fontSize = '14px';
								show_code_button.style.borderRadius = '7px';
								show_code_button.style.padding = '5px 10px';
								show_code_button.style.margin = '5px';
								show_code_button.style.display = 'inline-block';
								show_code_button.style.minHeight = 'auto';
								show_code_button.style.minWidth = '130px';
								show_code_button.style.lineHeight = '20px';
								show_code_button.style.verticalAlign = 'middle';
								show_code_button.style.width = 'auto';

								element.appendChild(button);

								alignWaitWithServer();
								var n=1e3*traffic_wait_time;
								window.localStorage.setItem(cache_time,n);
								var clickHandler = ('ontouchstart' in document.documentElement ? "touchstart" : "click");


								button.addEventListener('mouseenter', e => {
									button.style.background = '#c40b11';
								});

								button.addEventListener('mouseleave', e => {
									button.style.background = '#0bf405';
								});

								button.addEventListener('mousedown', e => {
									button.style.background = '#9a070d';
								});

								button.addEventListener('mouseup', e => {
									button.style.background = '#0bf405';
								});

								button.addEventListener(clickHandler, function(event){
									event.preventDefault();
									detectIncognito().then((result) => {
										if(applyPrivateModeIfNeeded(element, result)){
											return;
										}else{
											show_code_button.innerHTML= get_code_after_string + ' ' + n/1e3;
											element.innerHTML='';
											element.appendChild(show_code_button);
											element.dataset.time = traffic_wait_time;
											element.dataset.click = 'true';
											createSolution1Timer(show_code_button, element);
										}
									});
									return false;
								});
							}
						},
						(event) => {
							console.log(event);
						},
						() => {

						});
				}
			}
			else if(randomSolution == 1){
				var step = window.localStorage.getItem(count_step);
				if (step === null) {
					step = 1;
				}
				var flatform = 'tructiep';
				if (step == 1) {
					const referrer = getReferrer();
					flatform = checkReferer(referrer);
					console.log("check solution 2 flatform = " + flatform);
					window.localStorage.setItem(cache_flatform,flatform);
				}
				else{
					flatform = window.localStorage.getItem(cache_flatform);
				}
				if(typeof step === 'string') step = parseInt(step);
				step = step + 1;
				window.localStorage.setItem(count_step,step);
				var isContinuation = step > 2;

				if(flatform != 'clicklink'){
					check_ref =true;
					ajaxGet(
						buildCampainUrl(flatform, 2, 2, isContinuation),
						(result) => {
							traffic_id = result.id;
							campaignTimeOnSite = Number(result.timeOnSitePerView) || 0;
							var element = document.getElementById(traffic_key);
							var numberPositionRandom = Math.floor(Math.random() * 9) + 4;
							var widthRan = Math.floor(numberPositionRandom *100 /12);
							var numberFloatRandom = Math.floor((Math.random() * 2));
							var styleFloat = numberFloatRandom == 0 ? 'left' : 'right';
							var styleRandom = document.createElement('style');
							styleRandom.type = 'text/css';
							styleRandom.innerHTML = '.colRan-' +  numberPositionRandom + ' { width:' + widthRan + '%;flex:0 0 auto;float:'+styleFloat+'}';
							document.getElementsByTagName('head')[0].appendChild(styleRandom);
							var numberAlignRandom = Math.floor(Math.random() * 3);
							var alignText = numberAlignRandom == 0 ? 'left !important' : (numberAlignRandom == 1 ? 'center !important' : 'right !important');
							var styleAlignRandom = document.createElement('style');
							styleAlignRandom.type = 'text/css';
							styleAlignRandom.innerHTML = '.alignRan' + ' { text-align:' + alignText + ';}';
							document.getElementsByTagName('head')[0].appendChild(styleAlignRandom);
							element.classList.add('colRan-' +  numberPositionRandom);
							element.classList.add('alignRan');

							//start solution 2: 2 trang, không lấy timeOnSite
							// trang 1 (step 2): 50–80s; trang 2: 30–60s sau khi click bài viết + LAYMA lại
							if(step == 2){
								traffic_wait_time = randomIntInclusive(50, 80);
								timeSangManHinh = Math.floor(Math.random() * 10) + 20;
							}
							else{
								traffic_wait_time = randomIntInclusive(30, 60);
								timeSangManHinh = Math.floor(Math.random() * 20) + 10;
							}


							applyServerWaitSession(result, !isContinuation);
							if(element
								&& check_ref
								&& get_code
							){
								//showElementToClickScreen();
								loaded_script = true;

								// element.style.background = '#fff';
								element.style.padding = '5px';
								element.style.color = '#000';
								element.style.position = 'relative';
								element.style.clear = 'both';


								var button = document.createElement("span");
								button.innerHTML = '<span style="display:inline-block;vertical-align:middle;color:#fff">' + get_code_string + '</span>';
								button.style.background = '#0bf405';
								button.style.border = '1px solid #fff';
								button.style.color = '#fff';
								button.style.fontWeight = '700';
								button.style.fontSize = '14px';
								button.style.borderRadius = '7px';
								button.style.padding = '5px 10px';
								button.style.margin = '5px';
								button.style.minHeight = 'auto';
								button.style.lineHeight = '20px';
								button.style.verticalAlign = 'middle';
								button.style.width = 'auto';
								button.style.cursor = 'pointer';
								button.style.display = 'inline-block';

								var show_code_button = document.createElement("div");
								show_code_button.innerHTML = '';
								show_code_button.style.background = '#0bf405';
								show_code_button.style.border = '1px solid #fff';
								show_code_button.style.color = '#fff';
								show_code_button.style.fontWeight = '700';
								show_code_button.style.fontSize = '14px';
								show_code_button.style.borderRadius = '7px';
								show_code_button.style.padding = '5px 10px';
								show_code_button.style.margin = '5px';
								show_code_button.style.display = 'inline-block';
								show_code_button.style.minHeight = 'auto';
								show_code_button.style.minWidth = '130px';
								show_code_button.style.lineHeight = '20px';
								show_code_button.style.verticalAlign = 'middle';
								show_code_button.style.width = 'auto';

								element.appendChild(button);

								alignWaitWithServer();
								var n=1e3*traffic_wait_time;
								window.localStorage.setItem(cache_time,n);
								var clickHandler = ('ontouchstart' in document.documentElement ? "touchstart" : "click");


								button.addEventListener('mouseenter', e => {
									button.style.background = '#c40b11';
								});

								button.addEventListener('mouseleave', e => {
									button.style.background = '#0bf405';
								});

								button.addEventListener('mousedown', e => {
									button.style.background = '#9a070d';
								});

								button.addEventListener('mouseup', e => {
									button.style.background = '#0bf405';
								});

								button.addEventListener(clickHandler, function(event){
									event.preventDefault();
									detectIncognito().then((result) => {
										if(applyPrivateModeIfNeeded(element, result)){
											return;
										}else{
											show_code_button.innerHTML= get_code_after_string + ' ' + n/1e3;
											element.innerHTML='';
											element.appendChild(show_code_button);
											element.dataset.time = traffic_wait_time;
											element.dataset.click = 'true';
											createSolution2Timer(show_code_button, element, step);
										}
									});
									return false;
								});
							}
						},
						(event) => {
							console.log(event);
						},
						() => {

						});
				}
			}
			else if(randomSolution == 2){
				var step = window.localStorage.getItem(count_step);
				if (step === null) {
					step = 1;
				}
				var flatform = 'tructiep';
				if (step == 1) {
					const referrer = getReferrer();
					flatform = checkReferer(referrer);
					console.log("check solution 3 flatform = " + flatform);
					window.localStorage.setItem(cache_flatform,flatform);
				}
				else{
					flatform = window.localStorage.getItem(cache_flatform);
				}
				if(typeof step === 'string') step = parseInt(step);
				step = step + 1;
				window.localStorage.setItem(count_step,step);
				var isContinuation = step > 2;

				if(flatform != 'clicklink'){
					check_ref =true;
					ajaxGet(
						buildCampainUrl(flatform, 2, 3, isContinuation),
						(result) => {
							traffic_id = result.id;
							campaignTimeOnSite = Number(result.timeOnSitePerView) || 0;
							var element = document.getElementById(traffic_key);
							var numberPositionRandom = Math.floor(Math.random() * 9) + 4;
							var widthRan = Math.floor(numberPositionRandom *100 /12);
							var numberFloatRandom = Math.floor((Math.random() * 2));
							var styleFloat = numberFloatRandom == 0 ? 'left' : 'right';
							var styleRandom = document.createElement('style');
							styleRandom.type = 'text/css';
							styleRandom.innerHTML = '.colRan-' +  numberPositionRandom + ' { width:' + widthRan + '%;flex:0 0 auto;float:'+styleFloat+'}';
							document.getElementsByTagName('head')[0].appendChild(styleRandom);
							var numberAlignRandom = Math.floor(Math.random() * 3);
							var alignText = numberAlignRandom == 0 ? 'left !important' : (numberAlignRandom == 1 ? 'center !important' : 'right !important');
							var styleAlignRandom = document.createElement('style');
							styleAlignRandom.type = 'text/css';
							styleAlignRandom.innerHTML = '.alignRan' + ' { text-align:' + alignText + ';}';
							document.getElementsByTagName('head')[0].appendChild(styleAlignRandom);
							element.classList.add('colRan-' +  numberPositionRandom);
							element.classList.add('alignRan');

							//start solution 3
							if(step == 2){
								traffic_wait_time = Math.floor(Math.random() * 20) + 40;
								timeSangManHinh = Math.floor(Math.random() * 15) + 15;
							}
							else if(step == 3){
								traffic_wait_time = Math.floor(Math.random() * 20) + 20;
								timeSangManHinh = Math.floor(traffic_wait_time/2);
							}
							else{
								traffic_wait_time = Math.floor(Math.random() * 15) + 15;
								timeSangManHinh = Math.floor(traffic_wait_time/2);
							}

							applyServerWaitSession(result, !isContinuation);
							if(element
								&& check_ref
								&& get_code
							){
								//showElementToClickScreen();
								loaded_script = true;

								// element.style.background = '#fff';
								element.style.padding = '5px';
								element.style.color = '#000';
								element.style.position = 'relative';
								element.style.clear = 'both';


								var button = document.createElement("span");
								button.innerHTML = '<span style="display:inline-block;vertical-align:middle;color:#fff">' + get_code_string + '</span>';
								button.style.background = '#0bf405';
								button.style.border = '1px solid #fff';
								button.style.color = '#fff';
								button.style.fontWeight = '700';
								button.style.fontSize = '14px';
								button.style.borderRadius = '7px';
								button.style.padding = '5px 10px';
								button.style.margin = '5px';
								button.style.minHeight = 'auto';
								button.style.lineHeight = '20px';
								button.style.verticalAlign = 'middle';
								button.style.width = 'auto';
								button.style.cursor = 'pointer';
								button.style.display = 'inline-block';

								var show_code_button = document.createElement("div");
								show_code_button.innerHTML = '';
								show_code_button.style.background = '#0bf405';
								show_code_button.style.border = '1px solid #fff';
								show_code_button.style.color = '#fff';
								show_code_button.style.fontWeight = '700';
								show_code_button.style.fontSize = '14px';
								show_code_button.style.borderRadius = '7px';
								show_code_button.style.padding = '5px 10px';
								show_code_button.style.margin = '5px';
								show_code_button.style.display = 'inline-block';
								show_code_button.style.minHeight = 'auto';
								show_code_button.style.minWidth = '130px';
								show_code_button.style.lineHeight = '20px';
								show_code_button.style.verticalAlign = 'middle';
								show_code_button.style.width = 'auto';

								element.appendChild(button);

								alignWaitWithServer();
								var n=1e3*traffic_wait_time;
								window.localStorage.setItem(cache_time,n);
								var clickHandler = ('ontouchstart' in document.documentElement ? "touchstart" : "click");


								button.addEventListener('mouseenter', e => {
									button.style.background = '#c40b11';
								});

								button.addEventListener('mouseleave', e => {
									button.style.background = '#0bf405';
								});

								button.addEventListener('mousedown', e => {
									button.style.background = '#9a070d';
								});

								button.addEventListener('mouseup', e => {
									button.style.background = '#0bf405';
								});

								button.addEventListener(clickHandler, function(event){
									event.preventDefault();
									detectIncognito().then((result) => {
										if(applyPrivateModeIfNeeded(element, result)){
											return;
										}else{
											show_code_button.innerHTML= get_code_after_string + ' ' + n/1e3;
											element.innerHTML='';
											element.appendChild(show_code_button);
											element.dataset.time = traffic_wait_time;
											element.dataset.click = 'true';
											createSolution3Timer(show_code_button, element, step);
										}
									});
									return false;
								});
							}
						},
						(event) => {
							console.log(event);
						},
						() => {

						});
				}
			}
			else if (randomSolution == 3) {
				const referrer = getReferrer();
				var flatform = checkReferer(referrer);
				if(flatform != 'clicklink'){
					check_ref =true;
					ajaxGet(
						buildCampainUrl(flatform, 1, 1, false),
						(result) => {
							traffic_id = result.id;
							campaignTimeOnSite = Number(result.timeOnSitePerView) || 0;
							var element = document.getElementById(traffic_key);
							var numberPositionRandom = Math.floor(Math.random() * 9) + 4;
							var widthRan = Math.floor(numberPositionRandom *100 /12);
							var numberFloatRandom = Math.floor((Math.random() * 2));
							var styleFloat = numberFloatRandom == 0 ? 'left' : 'right';
							var styleRandom = document.createElement('style');
							styleRandom.type = 'text/css';
							styleRandom.innerHTML = '.colRan-' +  numberPositionRandom + ' { width:' + widthRan + '%;flex:0 0 auto;float:'+styleFloat+'}';
							document.getElementsByTagName('head')[0].appendChild(styleRandom);
							var numberAlignRandom = Math.floor(Math.random() * 3);
							var alignText = numberAlignRandom == 0 ? 'left !important' : (numberAlignRandom == 1 ? 'center !important' : 'right !important');
							var styleAlignRandom = document.createElement('style');
							styleAlignRandom.type = 'text/css';
							styleAlignRandom.innerHTML = '.alignRan' + ' { text-align:' + alignText + ';}';
							document.getElementsByTagName('head')[0].appendChild(styleAlignRandom);
							element.classList.add('colRan-' +  numberPositionRandom);
							element.classList.add('alignRan');

							//start solution 4
							traffic_wait_time = Math.floor(Math.random() * 60) + 300;
							//traffic_wait_time = 80 + Math.floor(Math.random() * 40);
							timeSangManHinhS4 = 30 + Math.floor(Math.random() * 30);
							timeToScrollUpS4 = traffic_wait_time - timeSangManHinhS4 - 5;
							timeToScrollDownS4 = timeToScrollUpS4 - (Math.floor(Math.random() * 50) + 50);
							timeToScrollUpS4_2 = timeToScrollDownS4 - (50 + Math.floor(Math.random() * 50));
							applyServerWaitSession(result, true);
							if(element
								&& check_ref
								&& get_code
							){
								//showElementToClickScreen();
								loaded_script = true;

								// element.style.background = '#fff';
								element.style.padding = '5px';
								element.style.color = '#000';
								element.style.position = 'relative';
								element.style.clear = 'both';


								var button = document.createElement("span");
								button.innerHTML = '<span style="display:inline-block;vertical-align:middle;color:#fff">' + get_code_string + '</span>';
								button.style.background = '#0bf405';
								button.style.border = '1px solid #fff';
								button.style.color = '#fff';
								button.style.fontWeight = '700';
								button.style.fontSize = '14px';
								button.style.borderRadius = '7px';
								button.style.padding = '5px 10px';
								button.style.margin = '5px';
								button.style.minHeight = 'auto';
								button.style.lineHeight = '20px';
								button.style.verticalAlign = 'middle';
								button.style.width = 'auto';
								button.style.cursor = 'pointer';
								button.style.display = 'inline-block';

								var show_code_button = document.createElement("div");
								show_code_button.innerHTML = '';
								show_code_button.style.background = '#0bf405';
								show_code_button.style.border = '1px solid #fff';
								show_code_button.style.color = '#fff';
								show_code_button.style.fontWeight = '700';
								show_code_button.style.fontSize = '14px';
								show_code_button.style.borderRadius = '7px';
								show_code_button.style.padding = '5px 10px';
								show_code_button.style.margin = '5px';
								show_code_button.style.display = 'inline-block';
								show_code_button.style.minHeight = 'auto';
								show_code_button.style.minWidth = '130px';
								show_code_button.style.lineHeight = '20px';
								show_code_button.style.verticalAlign = 'middle';
								show_code_button.style.width = 'auto';

								element.appendChild(button);

								alignWaitWithServer();
								var n=1e3*traffic_wait_time;
								window.localStorage.setItem(cache_time,n);
								var clickHandler = ('ontouchstart' in document.documentElement ? "touchstart" : "click");


								button.addEventListener('mouseenter', e => {
									button.style.background = '#c40b11';
								});

								button.addEventListener('mouseleave', e => {
									button.style.background = '#0bf405';
								});

								button.addEventListener('mousedown', e => {
									button.style.background = '#9a070d';
								});

								button.addEventListener('mouseup', e => {
									button.style.background = '#0bf405';
								});

								button.addEventListener(clickHandler, function(event){
									event.preventDefault();
									detectIncognito().then((result) => {
										if(applyPrivateModeIfNeeded(element, result)){
											return;
										}else{
											show_code_button.innerHTML= get_code_after_string + ' ' + n/1e3;
											element.innerHTML='';
											element.appendChild(show_code_button);
											element.dataset.time = traffic_wait_time;
											element.dataset.click = 'true';
											createSolution4Timer(show_code_button, element);
										}
									});
									return false;
								});
							}
						},
						(event) => {
							console.log(event);
						},
						() => {

						});
				}
			}
			else if(randomSolution == 4){
				var step = window.localStorage.getItem(count_step);
				if (step === null) {
					step = 1;
				}
				var flatform = 'tructiep';
				if (step == 1) {
					const referrer = getReferrer();
					flatform = checkReferer(referrer);
					console.log("check solution 4 flatform = " + flatform);
					window.localStorage.setItem(cache_flatform,flatform);
				}
				else{
					flatform = window.localStorage.getItem(cache_flatform);
				}
				if(typeof step === 'string') step = parseInt(step);
				step = step + 1;
				window.localStorage.setItem(count_step,step);
				var isContinuation = step > 2;

				if(flatform != 'clicklink'){
					check_ref =true;
					ajaxGet(
						buildCampainUrl(flatform, 2, 3, isContinuation),
						(result) => {
							traffic_id = result.id;
							campaignTimeOnSite = Number(result.timeOnSitePerView) || 0;
							var element = document.getElementById(traffic_key);
							var numberPositionRandom = Math.floor(Math.random() * 9) + 4;
							var widthRan = Math.floor(numberPositionRandom *100 /12);
							var numberFloatRandom = Math.floor((Math.random() * 2));
							var styleFloat = numberFloatRandom == 0 ? 'left' : 'right';
							var styleRandom = document.createElement('style');
							styleRandom.type = 'text/css';
							styleRandom.innerHTML = '.colRan-' +  numberPositionRandom + ' { width:' + widthRan + '%;flex:0 0 auto;float:'+styleFloat+'}';
							document.getElementsByTagName('head')[0].appendChild(styleRandom);
							var numberAlignRandom = Math.floor(Math.random() * 3);
							var alignText = numberAlignRandom == 0 ? 'left !important' : (numberAlignRandom == 1 ? 'center !important' : 'right !important');
							var styleAlignRandom = document.createElement('style');
							styleAlignRandom.type = 'text/css';
							styleAlignRandom.innerHTML = '.alignRan' + ' { text-align:' + alignText + ';}';
							document.getElementsByTagName('head')[0].appendChild(styleAlignRandom);
							element.classList.add('colRan-' +  numberPositionRandom);
							element.classList.add('alignRan');

							//start solution 4
							if(step == 2){
								traffic_wait_time = Math.floor(Math.random() * 20) + 100;
								timeSangManHinh = 30;
							}
							else if(step == 3){
								traffic_wait_time = Math.floor(Math.random() * 30) + 60;
								timeSangManHinh = 20;
							}
							else{
								traffic_wait_time = Math.floor(Math.random() * 50) + 100;
								timeSangManHinh = 25;
							}

							applyServerWaitSession(result, !isContinuation);
							if(element
								&& check_ref
								&& get_code
							){
								//showElementToClickScreen();
								loaded_script = true;

								// element.style.background = '#fff';
								element.style.padding = '5px';
								element.style.color = '#000';
								element.style.position = 'relative';
								element.style.clear = 'both';


								var button = document.createElement("span");
								button.innerHTML = '<span style="display:inline-block;vertical-align:middle;color:#fff">' + get_code_string + '</span>';
								button.style.background = '#0bf405';
								button.style.border = '1px solid #fff';
								button.style.color = '#fff';
								button.style.fontWeight = '700';
								button.style.fontSize = '14px';
								button.style.borderRadius = '7px';
								button.style.padding = '5px 10px';
								button.style.margin = '5px';
								button.style.minHeight = 'auto';
								button.style.lineHeight = '20px';
								button.style.verticalAlign = 'middle';
								button.style.width = 'auto';
								button.style.cursor = 'pointer';
								button.style.display = 'inline-block';

								var show_code_button = document.createElement("div");
								show_code_button.innerHTML = '';
								show_code_button.style.background = '#0bf405';
								show_code_button.style.border = '1px solid #fff';
								show_code_button.style.color = '#fff';
								show_code_button.style.fontWeight = '700';
								show_code_button.style.fontSize = '14px';
								show_code_button.style.borderRadius = '7px';
								show_code_button.style.padding = '5px 10px';
								show_code_button.style.margin = '5px';
								show_code_button.style.display = 'inline-block';
								show_code_button.style.minHeight = 'auto';
								show_code_button.style.minWidth = '130px';
								show_code_button.style.lineHeight = '20px';
								show_code_button.style.verticalAlign = 'middle';
								show_code_button.style.width = 'auto';

								element.appendChild(button);

								alignWaitWithServer();
								var n=1e3*traffic_wait_time;
								window.localStorage.setItem(cache_time,n);
								var clickHandler = ('ontouchstart' in document.documentElement ? "touchstart" : "click");


								button.addEventListener('mouseenter', e => {
									button.style.background = '#c40b11';
								});

								button.addEventListener('mouseleave', e => {
									button.style.background = '#0bf405';
								});

								button.addEventListener('mousedown', e => {
									button.style.background = '#9a070d';
								});

								button.addEventListener('mouseup', e => {
									button.style.background = '#0bf405';
								});

								button.addEventListener(clickHandler, function(event){
									event.preventDefault();
									detectIncognito().then((result) => {
										if(applyPrivateModeIfNeeded(element, result)){
											return;
										}else{
											show_code_button.innerHTML= get_code_after_string + ' ' + n/1e3;
											element.innerHTML='';
											element.appendChild(show_code_button);
											element.dataset.time = traffic_wait_time;
											element.dataset.click = 'true';
											createSolution5Timer(show_code_button, element, step);
										}
									});
									return false;
								});
							}
						},
						(event) => {
							console.log(event);
						},
						() => {

						});
				}
			}
		}
		jQuery(document).ready(initScript);
	}
	function isFirstLoad(namesp){
		var isFirst = namesp.firstLoad === undefined;
		namesp.firstLoad = false;
		return isFirst;
	};
	function checkScrollUpDown(show_code_button,element,typeCheck){
		showTrackingMessage('');
		updateCounterMessage('');
		if(typeCheck === 'scrollUp'){
			updateTrackingMessage(requiredScrollUp);
			updateCounterMessage(window.localStorage.getItem(cache_time)/1e3);
		}
		if(typeCheck === 'scrollDown'){
			updateTrackingMessage(requiredScrollDown);
			updateCounterMessage(window.localStorage.getItem(cache_time)/1e3);
		}

		let typeScr = 'any';
		let previousScrollPosition = window.pageYOffset || document.documentElement.scrollTop;
		const detectScrollType = () => {
			let type = '';

			let scrollPosition = window.pageYOffset || document.documentElement.scrollTop;
			if (scrollPosition > previousScrollPosition) {
				type = 'scrollDown';
			} else if (scrollPosition < previousScrollPosition) {
				type = 'scrollUp';
			}
			previousScrollPosition = scrollPosition;

			return type;
		};

		const scrollHandler = (event) => {
			const scrollType = detectScrollType();
			if (scrollType === 'scrollUp' && typeCheck === 'scrollUp' && (document.documentElement.scrollTop <= 0 || window.pageYOffset <= 0)) {
				window.removeEventListener('scroll', scrollHandler);
				var n = window.localStorage.getItem(cache_time);
				updateTrackingMessage('Tiếp tục lấy mã sau:');
				createScrollTimer(show_code_button, element, 'down');
			}
			if (scrollType === 'scrollDown' && typeCheck === 'scrollDown' && ((window.innerHeight + window.pageYOffset + 2) >= document.body.offsetHeight)) {
				window.removeEventListener('scroll', scrollHandler);
				var n = window.localStorage.getItem(cache_time);
				updateTrackingMessage('Tiếp tục lấy mã sau:');
				createFinalSolution1Timer(show_code_button, element);
			}
		}
		window.addEventListener('scroll', scrollHandler);
	}
	function checkClickManHinh(show_code_button,element,scroll=''){
		var clickHandler = ('ontouchstart' in document.documentElement ? "touchstart" : "click");
		updateTrackingMessage('Chạm vào màn hình để lấy mã');
		updateCounterMessage(window.localStorage.getItem(cache_time)/1e3);
		const clickManHinh = () =>{
			window.removeEventListener(clickHandler, clickManHinh);
			var n = window.localStorage.getItem(cache_time);
			updateTrackingMessage('Tiếp tục lấy mã sau:');
			createClickScreenTimer(show_code_button, element, scroll);
		}
		window.addEventListener(clickHandler, clickManHinh);

	}
	function checkClickManHinhSolution2(show_code_button,element,step){
		var clickHandler = ('ontouchstart' in document.documentElement ? "touchstart" : "click");
		updateTrackingMessage('Chạm vào màn hình để lấy mã');
		updateCounterMessage(window.localStorage.getItem(cache_time)/1e3);
		const clickManHinh2 = () =>{
			window.removeEventListener(clickHandler, clickManHinh2);
			var n = window.localStorage.getItem(cache_time);
			updateTrackingMessage('Tiếp tục lấy mã sau:');
			createSolution2ClickScreenTimer(show_code_button, element, step);
		}
		window.addEventListener(clickHandler, clickManHinh2);
	}
	function checkClickManHinhSolution3(show_code_button,element,step){
		var clickHandler = ('ontouchstart' in document.documentElement ? "touchstart" : "click");
		updateTrackingMessage('Chạm vào màn hình để lấy mã');
		updateCounterMessage(window.localStorage.getItem(cache_time)/1e3);
		const clickManHinh1 = () =>{
			window.removeEventListener(clickHandler, clickManHinh1);
			var n = window.localStorage.getItem(cache_time);
			updateTrackingMessage('Tiếp tục lấy mã sau:');
			createSolution3ClickScreenTimer(show_code_button, element, step);
		}
		window.addEventListener(clickHandler, clickManHinh1);
	}
	function checkButtonClick(step = 4){
		if (haltIfSpeedHack()) {
			return;
		}

		if (step >= 4) {
			document.getElementById("xacthucButton").style.display = "block";
			var element = document.getElementById(traffic_key);
			var solution = window.localStorage.getItem(cache_solution);
			if (canOpenGetCode(element)) {
				showCaptchaModalForGetCode(element, solution);
			}
		}
		else{
			if(step == 3){
				updateTrackingMessage(requiredClickPost1);
			}
			else{
				updateTrackingMessage(requiredClickPost);
			}
			
		}

	}
	function checkButtonClickSolution2(step = 3){
		if (haltIfSpeedHack()) {
			return;
		}

		if (step >= 3) {
			document.getElementById("xacthucButton").style.display = "block";
			var element = document.getElementById(traffic_key);
			var solution = window.localStorage.getItem(cache_solution);
			if (canOpenGetCode(element)) {
				showCaptchaModalForGetCode(element, solution);
			}
		}
		else{
			updateTrackingMessage(requiredClickPostSolution2);
		}

	}
	function saveComment(flatform){
		var acc = document.getElementById("accountCmt").value;
		var mess = document.getElementById("messageCmt").value;
		ajaxPost(
					apiUrl + "/api/admin/comment/create",
					{
						account: acc,
						message: mess
					},
					(result) => {
						hideErrorComment();
						getComment();
						if(flatform == 'tructiep'){
							console.log('tructiep');
							// Show captcha modal for direct traffic
							var element = document.getElementById(traffic_key);
							showCaptchaModalForGetCode(element, "1");
						}
					},
					(event) => {
						console.log(event);
					},
					() => {

					});
	}
	function displayErrorComment(error){
		document.getElementById('error-display').style.display="block";
		document.getElementById('error-display').innerHTML=error;
	}
	function hideErrorComment(){
		document.getElementById('error-display').style.display="none";
	}
	function getComment(){
		ajaxGet(
					apiUrl + "/api/admin/comment/pagingComment?pageIndex=1",
					(result) => {
						console.log(result);
						displayComment(result.results);
					},
					(event) => {
						console.log(event);
					},
					() => {

					});
	}
	function displayComment(data){
		var htmlCmt = '';
		for (let i = 0; i < data.length; i++) {
		  var mydate = new Date(data[i].dateCreated);
		  htmlCmt += '<div class="flex-row align-top"><div class="flex-col flex-grow"><div class="title-cmt"><span class="author-name uppercase">' + data[i].account + '</span><span class="pull-right">'+ mydate.toLocaleTimeString() +'</span></div><p class="author-desc small">' + data[i].message +'</p></div></div>';
		  if(i == data.length - 1){
			  document.getElementById('topCmt').innerHTML = htmlCmt;
		  }
		}
	}
	function onchange (evt) {
		var v = "visible", h = "hidden",
		evtMap = {
			focus:v, focusin:v, pageshow:v, blur:h, focusout:h, pagehide:h
		};
		evt = evt || window.event;
		if (evt.type in evtMap)
			traffic_blurred = evtMap[evt.type] == 'hidden';
		else
			traffic_blurred = this[hidden] ? 1 : 0;
	}
	function copyTextToClipboard(text){
		var textArea = document.createElement("textarea");

		textArea.style.position = 'fixed';
		textArea.style.top = 0;
		textArea.style.left = 0;

		textArea.style.width = '2em';
		textArea.style.height = '2em';

		textArea.style.padding = 0;

		textArea.style.border = 'none';
		textArea.style.outline = 'none';
		textArea.style.boxShadow = 'none';

		textArea.style.background = 'transparent';
		textArea.value = text;
		document.body.appendChild(textArea);

		textArea.select();

		var successful = false;
		try {
			var tmp = document.oncopy;
			document.oncopy = function(){};
			successful = document.execCommand('copy');
			document.oncopy = tmp;
		} catch (err) {
		}
		document.body.removeChild(textArea);
		return successful;
	}

	function createTooltip(text){

		var tooltip = document.createElement("div");
		tooltip.style.top = '-7px';
		tooltip.style.left = '50%';
		tooltip.style.display = 'block';
		tooltip.style.transform = 'translate(-50%,-50%)';
		tooltip.style.padding = '5px 0';
		tooltip.style.opacity = '0.9';
		tooltip.style.position = 'absolute';

		var arrow = document.createElement("div");
		arrow.style.left = '50%';
		arrow.style.bottom = '0';
		arrow.style.marginLeft = '-5px';
		arrow.style.borderWidth = '5px 5px 0';
		arrow.style.position = 'absolute';
		arrow.style.width = '0';
		arrow.style.height = '0';
		arrow.style.borderColor = 'transparent';
		arrow.style.borderStyle = 'solid';
		arrow.style.borderTopColor = '#000';

		var inner = document.createElement("div");
		inner.style.padding = '3px 8px';
		inner.style.color = '#fff';
		inner.style.textAlign = 'center';
		inner.style.backgroundColor = '#000';
		inner.style.borderRadius = '4px';
		inner.innerHTML = text;

		tooltip.appendChild(arrow);
		tooltip.appendChild(inner);

		return tooltip;
	}
	function checkAdsClick(){
		var ads_click = false;
		var url_string = window.location.href;
		var url = new URL(url_string);

		if(url.searchParams.get('gclid') != null){
			ads_click = true;
		}
		return ads_click;
	}
	var detectIncognito = function () {
		var run = function () {
			return new Promise(function (resolve) {
				var browserName = "Unknown";
				var callbackSettled = false;
				function __callback(isPrivate) {
					if (callbackSettled) {
						return;
					}
					callbackSettled = true;
					resolve({ isPrivate: isPrivate, browserName: browserName });
				}
				function identifyChromium() {
					var ua = navigator.userAgent;
					if (ua.match(/Chrome/)) {
						if (navigator.brave !== undefined) {
							return "Brave";
						}
						if (ua.match(/Edg/)) {
							return "Edge";
						}
						if (ua.match(/OPR/)) {
							return "Opera";
						}
						return "Chrome";
					}
					return "Chromium";
				}
				function feid() {
					var toFixedEngineID = 0;
					var neg = parseInt("-1", 10);
					try {
						neg.toFixed(neg);
					} catch (e) {
						toFixedEngineID = e.message.length;
					}
					return toFixedEngineID;
				}
				function isSafari() {
					return feid() === 44 || feid() === 43;
				}
				function isChrome() {
					return feid() === 51;
				}
				function isFirefox() {
					return feid() === 25;
				}
				function isMSIE() {
					return navigator.msSaveBlob !== undefined;
				}
				async function currentSafariTest() {
					try {
						await navigator.storage.getDirectory();
						__callback(false);
					} catch (e) {
						var safariMessage = e instanceof Error && typeof e.message === "string" ? e.message : String(e);
						__callback(safariMessage.indexOf("unknown transient reason") !== -1);
					}
				}
				function safari13to18Test() {
					var tmp = String(Math.random());
					try {
						var dbReq = indexedDB.open(tmp, 1);
						dbReq.onupgradeneeded = function (ev) {
							var db = ev.target.result;
							try {
								db.createObjectStore("t", { autoIncrement: true }).put(new Blob());
								__callback(false);
							} catch (err) {
								var blobMessage = err instanceof Error && typeof err.message === "string" ? err.message : String(err);
								__callback(blobMessage.indexOf("are not yet supported") !== -1);
							} finally {
								db.close();
								indexedDB.deleteDatabase(tmp);
							}
						};
						dbReq.onerror = function () {
							__callback(false);
						};
					} catch (e) {
						__callback(false);
					}
				}
				function oldSafariTest() {
					var openDB = window.openDatabase;
					var storage = window.localStorage;
					try {
						openDB(null, null, null, null);
					} catch (e) {
						__callback(true);
						return;
					}
					try {
						storage.setItem("test", "1");
						storage.removeItem("test");
					} catch (e) {
						__callback(true);
						return;
					}
					__callback(false);
				}
				async function safariPrivateTest() {
					if (navigator.storage && typeof navigator.storage.getDirectory === "function") {
						await currentSafariTest();
					} else if (navigator.maxTouchPoints !== undefined) {
						safari13to18Test();
					} else {
						oldSafariTest();
					}
				}
				function chromePrivateTest() {
					var PAYLOAD = 16384;
					var WRITES = 15;
					var ROUNDS = 15;
					var MIN_ROUNDS = 7;
					var CAP_MS = 1000;
					var THRESHOLD = 1.30;
					var dbName = "__di_" + Math.random().toString(36).slice(2);
					var payload = new Uint8Array(PAYLOAD);
					var req = indexedDB.open(dbName, 1);
					req.onupgradeneeded = function () {
						req.result.createObjectStore("s");
					};
					req.onerror = function () {
						indexedDB.deleteDatabase(dbName);
						__callback(false);
					};
					req.onsuccess = function () {
						var db = req.result;
						var honored = false;
						try {
							var probe = db.transaction("s", "readwrite", { durability: "strict" });
							honored = probe.durability === "strict";
							probe.abort();
						} catch (e) { }
						if (!honored) {
							db.close();
							indexedDB.deleteDatabase(dbName);
							__callback(false);
							return;
						}
						var block = function (durability) {
							return new Promise(function (resolveBlock, rejectBlock) {
								var t0 = performance.now();
								var i = 0;
								var step = function () {
									if (i === WRITES) {
										resolveBlock(performance.now() - t0);
										return;
									}
									var tx = db.transaction("s", "readwrite", { durability: durability });
									tx.objectStore("s").put(payload, i);
									i++;
									tx.oncomplete = step;
									tx.onerror = tx.onabort = function () {
										rejectBlock(tx.error);
									};
								};
								step();
							});
						};
						(async function () {
							var start = performance.now();
							await block("relaxed");
							await block("strict");
							var ratios = [];
							for (var r = 0; r < ROUNDS; r++) {
								var rel = await block("relaxed");
								var str = await block("strict");
								ratios.push(rel > 0 ? str / rel : Infinity);
								if (ratios.length >= MIN_ROUNDS && performance.now() - start >= CAP_MS) {
									break;
								}
							}
							ratios.sort(function (a, b) { return a - b; });
							db.close();
							indexedDB.deleteDatabase(dbName);
							__callback(ratios[ratios.length >> 1] < THRESHOLD);
						})().catch(function () {
							db.close();
							indexedDB.deleteDatabase(dbName);
							__callback(false);
						});
					};
				}
				async function firefoxPrivateTest() {
					if (navigator.storage && typeof navigator.storage.getDirectory === "function") {
						try {
							await navigator.storage.getDirectory();
							__callback(false);
						} catch (e) {
							var ffMessage = e instanceof Error && typeof e.message === "string" ? e.message : String(e);
							__callback(ffMessage.indexOf("Security error") !== -1);
						}
						return;
					}
					var request = indexedDB.open("inPrivate");
					request.onerror = function (event) {
						if (request.error && request.error.name === "InvalidStateError") {
							event.preventDefault();
							__callback(true);
							return;
						}
						__callback(false);
					};
					request.onsuccess = function () {
						indexedDB.deleteDatabase("inPrivate");
						__callback(false);
					};
				}
				function msiePrivateTest() {
					__callback(window.indexedDB === undefined);
				}
				async function main() {
					if (isSafari()) {
						browserName = "Safari";
						await safariPrivateTest();
					} else if (isChrome()) {
						browserName = identifyChromium();
						chromePrivateTest();
					} else if (isFirefox()) {
						browserName = "Firefox";
						await firefoxPrivateTest();
					} else if (isMSIE()) {
						browserName = "Internet Explorer";
						msiePrivateTest();
					} else {
						__callback(false);
					}
				}
				main().catch(function () {
					__callback(false);
				});
			});
		};
		return Promise.race([
			run(),
			new Promise(function (resolve) {
				setTimeout(function () {
					resolve({ isPrivate: false, browserName: "timeout" });
				}, 2500);
			})
		]);
	};
})();
