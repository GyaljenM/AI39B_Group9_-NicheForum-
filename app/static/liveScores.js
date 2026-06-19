/* liveScores.js — live World Cup scoreboard for the /live page.
 *
 * Polls our OWN backend (/api/live), which proxies football-data.org
 * server-side. That keeps the API token on the server and avoids the CORS
 * block football-data.org applies to direct browser calls.
 *
 * The JSON payload (see app/services/worldcup.py) looks like:
 *   {
 *     source, message, competition, live_count, goals_today,
 *     matches:  [ {match}, ... ],   // primary grid (live, or next fixtures)
 *     upcoming: [ {match}, ... ],   // next kickoffs for the timeline
 *     updated:  "2026-06-19T17:30:00Z"
 *   }
 * where each {match} is:
 *   { id, status, is_live, utc_date, stage, group, matchday,
 *     home: {name, short, crest, goals}, away: {name, short, crest, goals} }
 *
 * It populates:
 *   #match-grid        — the live/featured match cards
 *   #upcoming-list     — the "Upcoming" timeline
 *   #featured-*        — the big featured match card
 *   #live-count, #goals-today (+ #side-* mirrors) — the counters
 *   #live-updated      — status / "last updated" line
 *
 * Auto-refresh: 30 seconds.
 */

(function () {
    'use strict';

    var API_URL = '/api/live';
    var REFRESH_MS = 30000;

    var fetchController = null;

    // ── Interactive state (Goal Alerts / Match Details) ─────────────────────
    var alertsOn = false;            // are goal alerts armed?
    var detailsOpen = false;         // is the details panel expanded?
    var prevGoals = {};              // match id -> last seen {home, away}
    var primed = false;              // skip alerts on the very first poll
    var LAST = { featured: null, competition: 'FIFA World Cup' };
    var expandedCards = {};          // match id -> true when its card is expanded
    var footballUrl = '/communities';// where "Discuss" sends people (set from DOM)
    try { alertsOn = localStorage.getItem('wcGoalAlerts') === '1'; } catch (e) {}

    // ── Small helpers ──────────────────────────────────────────────────────
    function el(id) { return document.getElementById(id); }

    function escapeHtml(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    // Deterministic gradient from a team name, used as a crest fallback.
    function colorFromString(s, alt) {
        s = s || '';
        var hash = 0;
        for (var i = 0; i < s.length; i++) hash = s.charCodeAt(i) + ((hash << 5) - hash);
        var h1 = ('000000' + (hash & 0xFFFFFF).toString(16)).slice(-6);
        var h2 = ('000000' + ((hash >> 8) & 0xFFFFFF).toString(16)).slice(-6);
        return alt ? ('#' + h2) : ('#' + h1);
    }
    function gradientFor(name) {
        return 'background: linear-gradient(135deg,' + colorFromString(name, false) + ',' + colorFromString(name, true) + ');';
    }

    // Format an ISO timestamp as a local HH:MM (kickoff time for fixtures).
    function kickoffTime(iso) {
        if (!iso) return '';
        var d = new Date(iso);
        if (isNaN(d.getTime())) return '';
        return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    // Short status label shown in the match clock chip.
    function clockLabel(m) {
        switch (m.status) {
            case 'IN_PLAY': return 'LIVE';
            case 'PAUSED': return 'HT';
            case 'SUSPENDED': return 'SUSP';
            case 'FINISHED':
            case 'AWARDED': return 'FT';
            default: return kickoffTime(m.utc_date) || 'TBD'; // SCHEDULED / TIMED
        }
    }

    // Score string. Before kickoff there are no goals, so show "vs".
    function scoreText(m) {
        var h = m.home && m.home.goals;
        var a = m.away && m.away.goals;
        if (h == null || a == null) return 'vs';
        return h + ' - ' + a;
    }

    function leagueLabel(m) {
        var parts = [];
        if (m.stage) parts.push(m.stage);
        if (m.group) parts.push(m.group);
        return parts.join(' · ') || 'World Cup';
    }

    // A crest: real image if the API gave one, else a gradient tile with a shield.
    function crestHtml(team, big) {
        var size = big ? 'width:100%;height:100%;object-fit:contain;' : 'width:100%;height:100%;object-fit:contain;';
        if (team && team.crest) {
            return '<img src="' + escapeHtml(team.crest) + '" alt="' + escapeHtml(team.name) +
                '" style="' + size + 'padding:8px;" loading="lazy">';
        }
        var icon = big ? 'text-3xl' : 'text-xl';
        return '<span class="material-symbols-outlined text-white ' + icon +
            '" style="font-variation-settings:\'FILL\' 1;">shield</span>';
    }

    // ── Rendering ──────────────────────────────────────────────────────────
    function renderFeatured(m) {
        if (!m) return;
        var stageEl = el('featured-stage');
        if (stageEl) stageEl.textContent = leagueLabel(m);

        var minEl = el('featured-min');
        if (minEl) minEl.textContent = clockLabel(m);

        var scoreEl = el('featured-score');
        if (scoreEl) {
            var changed = scoreChanged(m);
            scoreEl.textContent = scoreText(m);
            if (changed) {
                scoreEl.classList.remove('score-flash');
                void scoreEl.offsetWidth;        // restart the animation
                scoreEl.classList.add('score-flash');
            }
        }

        var vsEl = el('featured-state');
        if (vsEl) vsEl.textContent = m.is_live ? 'LIVE' : (m.status === 'FINISHED' ? 'FULL TIME' : 'UPCOMING');

        var teams = document.querySelectorAll('#featured-teams .featured-team');
        if (teams.length >= 2) {
            applyFeaturedTeam(teams[0], m.home, m.utc_date, 'Home');
            applyFeaturedTeam(teams[1], m.away, m.utc_date, 'Away');
        }
    }

    function applyFeaturedTeam(node, team, iso, side) {
        var crest = node.querySelector('.team-crest');
        if (crest) {
            crest.setAttribute('style', team.crest ? 'background:#ffffff14;' : gradientFor(team.name));
            crest.innerHTML = crestHtml(team, true);
        }
        var ps = node.querySelectorAll('p');
        if (ps[0]) ps[0].textContent = team.name;
        if (ps[1]) ps[1].textContent = side;
    }

    function matchCardHtml(m) {
        var live = m.is_live;
        var clockClass = live ? 'match-clock-live' : 'match-clock-upcoming';
        var dot = live ? '<div class="live-dot-pulse" style="width:5px;height:5px;"></div>' : '';
        var leagueColor = colorFromString(leagueLabel(m));
        var flash = scoreChanged(m) ? ' score-flash' : '';
        var mid = m.id == null ? '' : String(m.id);

        return '' +
        '<div class="match-card reveal visible" data-sport="football" data-mid="' + escapeHtml(mid) + '" title="Tap for match details">' +
          '<div class="match-header">' +
            '<div class="match-league-badge">' +
              '<div class="match-league-dot" style="background:' + leagueColor + ';"></div>' +
              escapeHtml(leagueLabel(m)) +
            '</div>' +
            '<div style="display:flex;align-items:center;gap:8px;">' +
              '<div class="match-clock ' + clockClass + '">' + dot + escapeHtml(clockLabel(m)) + '</div>' +
              '<span class="material-symbols-outlined match-expand">expand_more</span>' +
            '</div>' +
          '</div>' +
          '<div class="match-body">' +
            '<div class="match-teams">' +
              teamCellHtml(m.home) +
              '<div class="match-score' + flash + '">' + escapeHtml(scoreText(m)) + '</div>' +
              teamCellHtml(m.away) +
            '</div>' +
          '</div>' +
          cardDetailsHtml(m) +
          '<div class="match-footer">' +
            '<a href="' + footballUrl + '" class="match-btn match-btn-primary">' +
              '<span class="material-symbols-outlined text-sm">forum</span>Discuss</a>' +
            '<button type="button" class="match-btn match-btn-secondary" data-action="toggle">' +
              '<span class="material-symbols-outlined text-sm">info</span>Details</button>' +
          '</div>' +
        '</div>';
    }

    function cChip(k, v) {
        if (v == null || v === '') return '';
        return '<div><div class="k">' + escapeHtml(k) + '</div><div class="v">' + escapeHtml(v) + '</div></div>';
    }
    function cardDetailsHtml(m) {
        var d = m.utc_date ? new Date(m.utc_date) : null;
        var when = d && !isNaN(d.getTime())
            ? d.toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' }) : 'TBD';
        return '<div class="match-details" hidden>' +
            cChip('Status', statusText(m.status)) +
            cChip('Kickoff', when) +
            cChip('Stage', m.stage) +
            cChip('Group', m.group) +
            cChip('Matchday', m.matchday != null ? ('MD ' + m.matchday) : null) +
        '</div>';
    }

    function scoreChanged(m) {
        if (!m || m.id == null) return false;
        var p = prevGoals[m.id];
        if (!p) return false;
        return (m.home.goals || 0) !== p.home || (m.away.goals || 0) !== p.away;
    }

    function teamCellHtml(team) {
        var style = team.crest ? 'background:#f5f5f4;' : gradientFor(team.name);
        return '' +
        '<div class="match-team">' +
          '<div class="match-team-crest" style="' + style + '">' + crestHtml(team, false) + '</div>' +
          '<p class="match-team-name">' + escapeHtml(team.name) + '</p>' +
        '</div>';
    }

    // Match threads aren't built yet — link to the Football community search so
    // the buttons go somewhere sensible rather than nowhere.
    function threadLink(m) {
        var q = encodeURIComponent((m.home.name || '') + ' ' + (m.away.name || ''));
        return '/search?q=' + q;
    }

    function emptyStateHtml(message) {
        return '' +
        '<div class="nf-card p-8 col-span-full text-center">' +
          '<span class="material-symbols-outlined text-4xl text-[#D6D3D1]">sports_soccer</span>' +
          '<p class="text-sm text-[#78716C] mt-3">' + escapeHtml(message || 'No matches to show right now.') + '</p>' +
        '</div>';
    }

    function renderGrid(matches, message) {
        var grid = el('match-grid');
        if (!grid) return;
        if (!matches || !matches.length) {
            grid.innerHTML = emptyStateHtml(message);
            return;
        }
        grid.innerHTML = matches.map(matchCardHtml).join('');
        // The grid is rebuilt every poll — restore any cards the user expanded.
        Object.keys(expandedCards).forEach(function (mid) {
            var card = grid.querySelector('.match-card[data-mid="' + cssEscape(mid) + '"]');
            if (card) setCardExpanded(card, true);
        });
    }

    // Minimal attribute-selector escaper (match ids are numeric, but be safe).
    function cssEscape(s) { return String(s).replace(/["\\]/g, '\\$&'); }

    function setCardExpanded(card, open) {
        var details = card.querySelector('.match-details');
        var chevron = card.querySelector('.match-expand');
        if (details) details.hidden = !open;
        if (chevron) chevron.classList.toggle('open', open);
        card.classList.toggle('expanded', open);
    }

    // One delegated handler for the whole grid: clicks toggle a card's details,
    // except when the click lands on the "Discuss" link (let it navigate).
    function wireGridExpand() {
        var grid = el('match-grid');
        if (!grid || grid.__wcWired) return;
        grid.__wcWired = true;
        grid.addEventListener('click', function (e) {
            if (e.target.closest('a')) return;          // Discuss link → navigate
            var card = e.target.closest('.match-card');
            if (!card) return;
            var mid = card.getAttribute('data-mid');
            var open = !card.classList.contains('expanded');
            setCardExpanded(card, open);
            if (mid) { if (open) expandedCards[mid] = true; else delete expandedCards[mid]; }
        });
    }

    function renderUpcoming(upcoming) {
        var list = el('upcoming-list');
        if (!list) return;
        if (!upcoming || !upcoming.length) {
            list.innerHTML = '<p class="text-sm text-[#A8A29E] px-2 py-4">No upcoming fixtures scheduled.</p>';
            return;
        }
        list.innerHTML = upcoming.map(function (m) {
            var d = m.utc_date ? new Date(m.utc_date) : null;
            var time = d && !isNaN(d.getTime()) ? kickoffTime(m.utc_date) : 'TBD';
            return '' +
            '<a href="' + threadLink(m) + '" class="upcoming-item">' +
              '<div class="upcoming-time">' +
                '<p class="text-sm font-bold text-[#1C1917]">' + escapeHtml(time) + '</p>' +
                '<p class="text-[10px] text-[#A8A29E] uppercase">Local</p>' +
              '</div>' +
              '<div class="flex items-center gap-3 flex-1">' +
                '<span class="material-symbols-outlined text-[#16a34a]" style="font-variation-settings:\'FILL\' 1;">sports_soccer</span>' +
                '<div class="upcoming-teams-info">' +
                  '<p class="text-sm font-semibold text-[#1C1917]">' + escapeHtml(m.home.name) + ' vs ' + escapeHtml(m.away.name) + '</p>' +
                  '<p class="text-xs text-[#A8A29E]">' + escapeHtml(leagueLabel(m)) + '</p>' +
                '</div>' +
              '</div>' +
              '<span class="material-symbols-outlined text-[#A8A29E] text-lg">chevron_right</span>' +
            '</a>';
        }).join('');
    }

    function setText(id, value) {
        var node = el(id);
        if (node) node.textContent = value;
    }

    function renderCounts(data) {
        setText('live-count', data.live_count);
        setText('side-live-count', data.live_count);
        setText('goals-today', data.goals_today);
        setText('side-goals-today', data.goals_today);
        // Sidebar "Today's Schedule" — real figures from the same payload.
        setText('schedule-live', data.live_count);
        setText('schedule-upcoming', (data.upcoming || []).length);
        setText('schedule-goals', data.goals_today);
    }

    function renderStatus(data) {
        var node = el('live-updated');
        if (!node) return;
        if (data.message) {
            node.textContent = data.message;
            return;
        }
        var d = data.updated ? new Date(data.updated) : null;
        var t = d && !isNaN(d.getTime()) ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '';
        node.textContent = t ? ('Live · updated ' + t) : 'Live';
    }

    function render(data) {
        LAST.competition = data.competition || LAST.competition;
        renderCounts(data);
        renderStatus(data);
        renderGrid(data.matches, data.message);
        renderUpcoming(data.upcoming);
        // Feature the first match in the primary list (a live one when available).
        LAST.featured = (data.matches && data.matches[0]) || null;
        renderFeatured(LAST.featured);
        detectGoals(data.matches || []);
        if (detailsOpen) renderDetails(LAST.featured);
    }

    // ── Goal detection → alerts ─────────────────────────────────────────────
    // Compare each live match's score against the previous poll. On the first
    // poll we just record the baseline (so we don't announce goals that were
    // already on the board when the page loaded).
    function detectGoals(matches) {
        matches.forEach(function (m) {
            if (!m || m.id == null) return;
            var now = { home: m.home.goals || 0, away: m.away.goals || 0 };
            var was = prevGoals[m.id];
            if (primed && alertsOn && was && m.is_live) {
                if (now.home > was.home) celebrateGoal(m, m.home, now);
                if (now.away > was.away) celebrateGoal(m, m.away, now);
            }
            prevGoals[m.id] = now;
        });
        primed = true;
    }

    function celebrateGoal(m, team, score) {
        var line = team.name + ' scored!  ' + m.home.name + ' ' + score.home + ' - ' + score.away + ' ' + m.away.name;
        showToast('⚽ GOAL!', line);
        beep();
        if ('Notification' in window && Notification.permission === 'granted') {
            try { new Notification('⚽ GOAL! ' + team.name, { body: line }); } catch (e) {}
        }
    }

    // ── Toast UI ─────────────────────────────────────────────────────────────
    function toastHost() {
        var host = el('wc-toasts');
        if (!host) {
            host = document.createElement('div');
            host.id = 'wc-toasts';
            document.body.appendChild(host);
        }
        return host;
    }
    function showToast(title, body) {
        var t = document.createElement('div');
        t.className = 'wc-toast';
        t.innerHTML = '<span class="material-symbols-outlined">sports_soccer</span>' +
            '<div><div style="font-size:14px;">' + escapeHtml(title) + '</div>' +
            '<div style="font-size:12px;font-weight:600;opacity:.9;">' + escapeHtml(body) + '</div></div>';
        toastHost().appendChild(t);
        setTimeout(function () {
            t.classList.add('out');
            setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 400);
        }, 5000);
    }

    // Short two-note chime via the Web Audio API (no asset needed).
    function beep() {
        try {
            var Ctx = window.AudioContext || window.webkitAudioContext;
            if (!Ctx) return;
            var ctx = new Ctx();
            [660, 880].forEach(function (freq, i) {
                var osc = ctx.createOscillator(), gain = ctx.createGain();
                osc.connect(gain); gain.connect(ctx.destination);
                osc.type = 'triangle';
                osc.frequency.value = freq;
                var t0 = ctx.currentTime + i * 0.16;
                gain.gain.setValueAtTime(0.0001, t0);
                gain.gain.exponentialRampToValueAtTime(0.25, t0 + 0.02);
                gain.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.15);
                osc.start(t0); osc.stop(t0 + 0.16);
            });
            setTimeout(function () { try { ctx.close(); } catch (e) {} }, 600);
        } catch (e) { /* audio blocked — toast still shows */ }
    }

    // ── Match Details panel ──────────────────────────────────────────────────
    function chip(k, v) {
        if (v == null || v === '') return '';
        return '<div class="detail-chip"><div class="k">' + escapeHtml(k) + '</div><div class="v">' + escapeHtml(v) + '</div></div>';
    }
    function renderDetails(m) {
        var panel = el('featured-details');
        if (!panel) return;
        if (!m) { panel.innerHTML = '<div class="detail-chip"><div class="v">No match selected.</div></div>'; return; }
        var kickoff = m.utc_date ? new Date(m.utc_date) : null;
        var when = kickoff && !isNaN(kickoff.getTime())
            ? kickoff.toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' })
            : 'TBD';
        panel.innerHTML =
            chip('Competition', LAST.competition) +
            chip('Status', statusText(m.status)) +
            chip('Kickoff (local)', when) +
            chip('Stage', m.stage) +
            chip('Group', m.group) +
            chip('Matchday', m.matchday != null ? ('MD ' + m.matchday) : null);
    }

    function statusText(status) {
        switch (status) {
            case 'IN_PLAY': return 'Live — in play';
            case 'PAUSED': return 'Half-time';
            case 'FINISHED':
            case 'AWARDED': return 'Full time';
            case 'SUSPENDED': return 'Suspended';
            case 'TIMED':
            case 'SCHEDULED': return 'Upcoming';
            default: return status || '—';
        }
    }

    // ── Controls ─────────────────────────────────────────────────────────────
    function paintAlertButton() {
        var btn = el('btn-goal-alert');
        if (!btn) return;
        btn.classList.toggle('alert-on', alertsOn);
        btn.setAttribute('aria-pressed', alertsOn ? 'true' : 'false');
        setText('goal-alert-label', alertsOn ? 'Goal Alerts: On' : 'Goal Alerts: Off');
        var icon = el('goal-alert-icon');
        if (icon) icon.textContent = alertsOn ? 'notifications_active' : 'notifications_off';
    }

    function setupControls() {
        var alertBtn = el('btn-goal-alert');
        if (alertBtn) {
            paintAlertButton();
            alertBtn.addEventListener('click', function () {
                alertsOn = !alertsOn;
                try { localStorage.setItem('wcGoalAlerts', alertsOn ? '1' : '0'); } catch (e) {}
                paintAlertButton();
                if (alertsOn) {
                    if ('Notification' in window && Notification.permission === 'default') {
                        Notification.requestPermission();
                    }
                    showToast('Goal Alerts on', 'You’ll be notified the moment a goal goes in.');
                    beep(); // also unlocks audio on this user gesture for later goals
                }
            });
        }

        var detailsBtn = el('btn-details');
        if (detailsBtn) {
            detailsBtn.addEventListener('click', function () {
                detailsOpen = !detailsOpen;
                var panel = el('featured-details');
                detailsBtn.setAttribute('aria-expanded', detailsOpen ? 'true' : 'false');
                if (panel) {
                    if (detailsOpen) { renderDetails(LAST.featured); panel.hidden = false; }
                    else { panel.hidden = true; }
                }
            });
        }

        var refreshBtn = el('btn-refresh');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', function () {
                var icon = el('btn-refresh-icon');
                if (icon) { icon.classList.remove('spin'); void icon.offsetWidth; icon.classList.add('spin'); }
                fetchAndRender();
            });
        }
    }

    // ── Fetch loop ───────────────────────────────────────────────────────────
    function fetchAndRender() {
        if (fetchController) fetchController.abort();
        fetchController = new AbortController();

        fetch(API_URL, { credentials: 'same-origin', signal: fetchController.signal })
            .then(function (res) {
                if (!res.ok) throw new Error('HTTP ' + res.status);
                return res.json();
            })
            .then(function (data) { if (data) render(data); })
            .catch(function (err) {
                if (err.name === 'AbortError') return; // expected on refresh
                console.warn('Failed to fetch live scores', err);
                var node = el('live-updated');
                if (node) node.textContent = 'Could not reach the score service — retrying…';
            });
    }

    function start() {
        var grid = el('match-grid');
        if (grid && grid.getAttribute('data-football-url')) {
            footballUrl = grid.getAttribute('data-football-url');
        }
        setupControls();
        wireGridExpand();
        fetchAndRender();
        setInterval(fetchAndRender, REFRESH_MS);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start);
    } else {
        start();
    }
})();
