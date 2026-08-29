/* ============================================================
   ATLAS console - live data layer.

   app.js ships a self-contained simulation so the console renders even as a
   standalone file. This layer replaces that simulation with the real ledger
   when the FastAPI backend is reachable, and silently leaves the simulation
   in place when it is not.
   ============================================================ */

'use strict';

(async function live() {
  const API = '';
  let connected = false;
  window.__atlasConnected = false;

  const displayText = (value) => String(value ?? '')
    .replaceAll('—', '-')
    .replaceAll('–', '-')
    .replaceAll(' · ', ', ');

  const get = async (path) => {
    const r = await fetch(API + path, { headers: { accept: 'application/json' } });
    if (!r.ok) throw new Error(`${path} → ${r.status}`);
    return r.json();
  };
  const post = async (path, body) => {
    const r = await fetch(API + path, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body || {}),
    });
    if (!r.ok) throw new Error(`${path} → ${r.status}`);
    return r.json();
  };

  /* ---------------------------------------------------- hydrate ledger */
  async function hydrate() {
    const [fleet, ctrls, agents, armor, mems, handoffs, events] = await Promise.all([
      get('/api/fleet'),
      get('/api/controls'),
      get('/api/agents'),
      get('/api/armor'),
      get('/api/memories'),
      get('/api/handoffs'),
      get('/api/events'),
    ]);

    // ---- controls -> the shape app.js renders
    controls.length = 0;
    for (const c of ctrls) {
      controls.push({
        id: c.id,
        group: c.group,
        name: displayText(c.name),
        domain: c.domain,
        owner: c.owner,
        status: c.status,
        ev: c.evidence_count,
        evTotal: c.evidence_required,
        when: relTime(c.updated_at),
      });
    }
    // keep the heatmap grouping in sync with whatever the ledger actually holds
    for (const k of Object.keys(CONTROL_GROUPS)) delete CONTROL_GROUPS[k];
    for (const c of controls) {
      (CONTROL_GROUPS[c.group] ||= []).push(c.id);
    }

    // ---- KPIs
    readiness = fleet.readiness_pct;
    autonomy = fleet.autonomy_pct;
    uptimeSec = fleet.uptime_seconds;
    window.__atlasFleet = fleet;

    // ---- registry
    AGENTS.length = 0;
    for (const a of agents) {
      AGENTS.push({
        id: a.name,
        v: a.version,
        fw: a.framework,
        spiffe: a.spiffe_id,
        scopes: a.scopes.length ? a.scopes : ['none'],
        inv: String(a.invocations),
        dept: a.departments,
        desc: displayText(a.description),
      });
    }

    // ---- memory bank
    MEMORIES.length = 0;
    for (const m of mems) {
      MEMORIES.push({
        text: displayText(m.text),
        src: displayText(m.source_run || m.scope),
        conf: m.confidence,
        reinforced: `${m.reinforced}×`,
      });
    }

    // ---- handoffs
    HANDOFFS.length = 0;
    for (const h of handoffs) {
      HANDOFFS.push({
        id: h.id,
        control: h.control_id,
        q: displayText(h.question),
        reason: displayText(h.reasoning || h.recommendation),
        sla: `escalates in ${Math.round(h.hours_remaining)}h`,
        stage: `${h.stage}/3`,
      });
    }

    // ---- activity stream: discard standalone simulation rows once live
    streamLog.length = 0;
    for (const e of events) {
      streamLog.push({
        t: new Date(e.at).toTimeString().slice(0, 8),
        a: e.agent,
        cls: classFor(e.agent),
        m: displayText(e.message),
        fresh: false,
      });
    }

    window.__atlasArmor = armor;
    connected = true;
    window.__atlasConnected = true;

    const connectionLabel = document.getElementById('connectionLabel');
    const environmentLabel = document.getElementById('environmentLabel');
    const workingCount = document.getElementById('workingCount');
    workingCount.textContent = String(fleet.by_status?.working || 0);
    if (fleet.runtime_mode === 'cloud') {
      connectionLabel.textContent = 'CLOUD LEDGER';
      environmentLabel.textContent = `cloud / ${fleet.cloud_location || 'configured region'}`;
    } else {
      connectionLabel.textContent = 'LOCAL DEMO';
      environmentLabel.textContent = 'local / seeded ledger';
    }
  }

  function relTime(iso) {
    const then = new Date(iso).getTime();
    const mins = Math.max(0, Math.round((Date.now() - then) / 60000));
    if (mins < 60) return `${mins}m ago`;
    if (mins < 1440) return `${Math.round(mins / 60)}h ago`;
    return `${Math.round(mins / 1440)}d ago`;
  }

  /* ------------------------------------------------------ live stream */
  const AGENT_CLASS = {
    orchestrator: 'a-orch', judge: 'a-judge', chaser: 'a-chaser',
    sentinel: 'a-sentinel', armor: 'a-armor', assembler: 'a-pkg',
  };
  function classFor(agent) {
    if (AGENT_CLASS[agent]) return AGENT_CLASS[agent];
    if (agent.startsWith('hunter')) return 'a-hunter';
    return 'a-orch';
  }

  function connectStream() {
    const es = new EventSource('/api/stream');
    es.onmessage = (msg) => {
      let e;
      try { e = JSON.parse(msg.data); } catch { return; }
      const row = {
        t: new Date(e.at).toTimeString().slice(0, 8),
        a: e.agent,
        cls: classFor(e.agent),
        m: displayText(e.message),
        fresh: true,
      };
      streamLog.unshift(row);
      if (streamLog.length > 40) streamLog.pop();
      const el = document.getElementById('stream');
      if (el) {
        el.insertAdjacentHTML('afterbegin', streamRow(row));
        if (el.children.length > 40) el.lastElementChild.remove();
      }
      // a ruling or a human answer changes the ledger - refresh quietly
      if (['ruled', 'answered', 'stale', 'swept'].includes(e.kind)) scheduleRefresh();
    };
    es.onerror = () => { /* EventSource retries on its own */ };
  }

  let refreshTimer = null;
  function scheduleRefresh() {
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(async () => {
      try { await hydrate(); go(route); } catch { /* keep last good state */ }
    }, 700);
  }

  /* ------------------------------------------- real actions on buttons */
  function wireActions() {
    document.addEventListener('click', async (e) => {
      const controlLink = e.target.closest('[data-control]');
      if (controlLink && connected) {
        e.stopPropagation();
        const id = controlLink.dataset.control;
        window.__atlasControlDetails ||= {};
        try {
          window.__atlasControlDetails[id] = await get(`/api/controls/${encodeURIComponent(id)}`);
          openControl(id);
        } catch (err) {
          delete window.__atlasControlDetails[id];
          openControl(id);
        }
        return;
      }

      const runBtn = e.target.closest('#runNow');
      if (runBtn && connected) {
        e.stopPropagation();
        runBtn.textContent = 'Running sweep';
        runBtn.disabled = true;
        runBtn.setAttribute('aria-busy', 'true');
        try {
          await post('/api/sweep', { limit_per_domain: 3 });
          await hydrate(); go('command');
        } catch (err) {
          runBtn.textContent = 'Sweep failed. Retry';
          runBtn.disabled = false;
          runBtn.removeAttribute('aria-busy');
        }
        return;
      }

      const approve = e.target.closest('[data-approve]');
      if (approve && connected) {
        e.stopPropagation();
        const id = approve.dataset.approve;
        approve.textContent = 'Approving';
        approve.disabled = true;
        try {
          await post(`/api/handoffs/${id}/answer`, { answer: 'approved' });
          await hydrate();
          go(route);
        } catch (err) {
          approve.textContent = 'Approval failed. Retry';
          approve.disabled = false;
        }
        return;
      }

      const reject = e.target.closest('[data-submit-rejection]');
      if (reject && connected) {
        e.stopPropagation();
        const id = reject.dataset.submitRejection;
        const input = document.querySelector(`[data-rejection-input="${id}"]`);
        const reason = input.value.trim();
        if (!reason) {
          input.setAttribute('aria-invalid', 'true');
          input.focus();
          return;
        }
        reject.textContent = 'Rejecting';
        reject.disabled = true;
        try {
          await post(`/api/handoffs/${id}/answer`, { answer: 'rejected', reason });
          await hydrate();
          go(route);
        } catch (err) {
          reject.textContent = 'Rejection failed. Retry';
          reject.disabled = false;
        }
        return;
      }

      const pkg = e.target.closest('#genPkg');
      if (pkg && connected) {
        e.stopPropagation();
        pkg.textContent = 'Assembling package';
        pkg.disabled = true;
        pkg.setAttribute('aria-busy', 'true');
        try {
          const manifest = await post('/api/package', {});
          window.__atlasPackage = manifest;
          downloadText('manifest.json', JSON.stringify(manifest, null, 2), 'application/json;charset=utf-8');
          await hydrate();
          if (route === 'package') {
            go('package');
            const refreshed = document.getElementById('genPkg');
            if (refreshed) refreshed.textContent = 'manifest.json downloaded';
          }
        } catch (err) {
          pkg.textContent = 'Package failed. Retry';
          pkg.disabled = false;
          pkg.removeAttribute('aria-busy');
          return;
        }
      }
    }, true);
  }

  /* ------------------------------------------------------------- boot */
  try {
    await hydrate();
  } catch (err) {
    console.info('ATLAS backend unreachable - running the built-in simulation.', err.message);
    return; // app.js simulation stays in charge
  }

  // Silence the simulated event generator; real events arrive over SSE.
  pushStream = function () {};

  connectStream();
  wireActions();
  go(route);
  console.info('ATLAS console connected to live ledger.');
})();
