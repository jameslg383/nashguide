// NashGuide Analytics Tracker v1.0
// Embed this in index.html before </body>
(function() {
  const API = window.location.origin + '/api/analytics/track';
  const SESSION_KEY = 'ng_sid';
  const VISITOR_KEY = 'ng_vid';

  // Generate unique IDs
  function uid() {
    return 'xxxxxxxx-xxxx-4xxx'.replace(/x/g, () => (Math.random()*16|0).toString(16));
  }

  // Get or create persistent visitor ID
  function getVisitorId() {
    let vid = localStorage.getItem(VISITOR_KEY);
    if (!vid) { vid = uid(); localStorage.setItem(VISITOR_KEY, vid); }
    return vid;
  }

  // Get or create session ID (expires after 30min inactivity)
  function getSessionId() {
    let data = JSON.parse(sessionStorage.getItem(SESSION_KEY) || 'null');
    const now = Date.now();
    if (!data || (now - data.ts) > 1800000) {
      data = { id: uid(), ts: now, pageviews: 0 };
    }
    data.ts = now;
    data.pageviews++;
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(data));
    return data;
  }

  // Device & browser fingerprint
  function getDeviceInfo() {
    const ua = navigator.userAgent;
    const nav = navigator;
    let device = 'desktop';
    if (/Mobi|Android/i.test(ua)) device = 'mobile';
    else if (/Tablet|iPad/i.test(ua)) device = 'tablet';

    let browser = 'other';
    if (ua.includes('Chrome') && !ua.includes('Edg')) browser = 'chrome';
    else if (ua.includes('Safari') && !ua.includes('Chrome')) browser = 'safari';
    else if (ua.includes('Firefox')) browser = 'firefox';
    else if (ua.includes('Edg')) browser = 'edge';

    let os = 'other';
    if (ua.includes('Windows')) os = 'windows';
    else if (ua.includes('Mac')) os = 'macos';
    else if (ua.includes('Linux')) os = 'linux';
    else if (/iPhone|iPad/.test(ua)) os = 'ios';
    else if (ua.includes('Android')) os = 'android';

    return {
      device, browser, os,
      user_agent: ua,
      screen_width: screen.width,
      screen_height: screen.height,
      viewport_width: window.innerWidth,
      viewport_height: window.innerHeight,
      pixel_ratio: window.devicePixelRatio || 1,
      language: nav.language,
      languages: Array.from(nav.languages || []),
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      touch: 'ontouchstart' in window,
      connection: nav.connection ? {
        type: nav.connection.effectiveType,
        downlink: nav.connection.downlink,
        rtt: nav.connection.rtt
      } : null,
      cores: nav.hardwareConcurrency || null,
      memory: nav.deviceMemory || null,
      platform: nav.platform
    };
  }

  // Parse UTM params & referrer
  function getTrafficSource() {
    const params = new URLSearchParams(window.location.search);
    return {
      referrer: document.referrer || 'direct',
      referrer_domain: document.referrer ? new URL(document.referrer).hostname : 'direct',
      utm_source: params.get('utm_source'),
      utm_medium: params.get('utm_medium'),
      utm_campaign: params.get('utm_campaign'),
      utm_term: params.get('utm_term'),
      utm_content: params.get('utm_content'),
      landing_page: window.location.pathname,
      full_url: window.location.href
    };
  }

  // Send event
  function track(event_type, data) {
    const session = getSessionId();
    const payload = {
      event_type,
      visitor_id: getVisitorId(),
      session_id: session.id,
      session_pageviews: session.pageviews,
      timestamp: new Date().toISOString(),
      page_url: window.location.pathname,
      ...data
    };
    // Use sendBeacon for reliability (survives page unload)
    const blob = new Blob([JSON.stringify(payload)], { type: 'application/json' });
    if (navigator.sendBeacon) {
      navigator.sendBeacon(API, blob);
    } else {
      fetch(API, { method: 'POST', body: blob, keepalive: true }).catch(() => {});
    }
  }

  // ===== AUTO-TRACKED EVENTS =====

  // 1. Page View (with full context on first view)
  const session = getSessionId();
  const isNewVisitor = session.pageviews <= 1;
  track('page_view', {
    device_info: getDeviceInfo(),
    traffic_source: getTrafficSource(),
    is_new_visitor: isNewVisitor
  });

  // 2. Scroll Depth Tracking
  let maxScroll = 0;
  const scrollMilestones = [25, 50, 75, 90, 100];
  const hitMilestones = new Set();
  window.addEventListener('scroll', function() {
    const scrollTop = window.scrollY || document.documentElement.scrollTop;
    const docHeight = document.documentElement.scrollHeight - window.innerHeight;
    const scrollPct = Math.round((scrollTop / docHeight) * 100);
    if (scrollPct > maxScroll) {
      maxScroll = scrollPct;
      scrollMilestones.forEach(m => {
        if (scrollPct >= m && !hitMilestones.has(m)) {
          hitMilestones.add(m);
          track('scroll_depth', { depth_pct: m });
        }
      });
    }
  }, { passive: true });

  // 3. Time on Page
  const pageStart = Date.now();
  let timeOnPage = 0;
  let isVisible = true;
  document.addEventListener('visibilitychange', function() {
    if (document.hidden) {
      timeOnPage += Date.now() - pageStart;
      isVisible = false;
    } else {
      isVisible = true;
    }
  });

  // Send time on page when leaving
  window.addEventListener('beforeunload', function() {
    const totalTime = timeOnPage + (isVisible ? Date.now() - pageStart : 0);
    track('page_exit', {
      time_on_page_ms: totalTime,
      time_on_page_seconds: Math.round(totalTime / 1000),
      max_scroll_pct: maxScroll
    });
  });

  // 4. Click Tracking (all clicks with context)
  document.addEventListener('click', function(e) {
    const el = e.target.closest('button, a, [data-track]');
    if (!el) return;
    const rect = el.getBoundingClientRect();
    track('click', {
      element_tag: el.tagName.toLowerCase(),
      element_text: (el.textContent || '').trim().substring(0, 100),
      element_class: el.className ? el.className.substring(0, 200) : '',
      element_id: el.id || null,
      data_track: el.getAttribute('data-track') || null,
      click_x: Math.round(e.clientX),
      click_y: Math.round(e.clientY),
      element_x: Math.round(rect.left),
      element_y: Math.round(rect.top),
      viewport_x: window.innerWidth,
      viewport_y: window.innerHeight
    });
  });

  // 5. Engagement signals
  let engaged = false;
  let engageTimer = setTimeout(function() {
    engaged = true;
    track('engaged_visitor', { time_to_engage_ms: 10000 });
  }, 10000);

  // 6. Performance metrics
  window.addEventListener('load', function() {
    setTimeout(function() {
      const perf = performance.getEntriesByType('navigation')[0];
      if (perf) {
        track('performance', {
          dns_ms: Math.round(perf.domainLookupEnd - perf.domainLookupStart),
          connect_ms: Math.round(perf.connectEnd - perf.connectStart),
          ttfb_ms: Math.round(perf.responseStart - perf.requestStart),
          dom_load_ms: Math.round(perf.domContentLoadedEventEnd - perf.navigationStart),
          full_load_ms: Math.round(perf.loadEventEnd - perf.navigationStart),
          transfer_size: perf.transferSize,
          dom_elements: document.getElementsByTagName('*').length
        });
      }
    }, 1000);
  });

  // ===== EXPOSE FOR MANUAL TRACKING =====
  // Use these in the React app to track funnel events
  window.ngTrack = track;

  // Convenience methods
  window.ngTrack.quizStart = () => track('quiz_start', {});
  window.ngTrack.quizStep = (step, answer) => track('quiz_step', { step_number: step, step_answer: answer });
  window.ngTrack.quizComplete = (answers) => track('quiz_complete', { answers });
  window.ngTrack.quizAbandon = (step) => track('quiz_abandon', { abandoned_at_step: step });
  window.ngTrack.tierView = () => track('tier_view', {});
  window.ngTrack.tierSelect = (tier, price) => track('tier_select', { tier_id: tier, price });
  window.ngTrack.checkoutStart = (tier, price) => track('checkout_start', { tier_id: tier, price });
  window.ngTrack.checkoutEmail = () => track('checkout_email_entered', {});
  window.ngTrack.paymentStart = (tier, price) => track('payment_start', { tier_id: tier, price });
  window.ngTrack.paymentSuccess = (tier, price, orderId) => track('payment_success', { tier_id: tier, price, order_id: orderId });
  window.ngTrack.paymentFail = (tier, error) => track('payment_fail', { tier_id: tier, error });
  window.ngTrack.waitlistSignup = (email) => track('waitlist_signup', { email_domain: email.split('@')[1] });

  console.log('[NashGuide Analytics] Tracking initialized');
})();
