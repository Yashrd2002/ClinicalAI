// =====================================================================
// AEGIS CLINICAL - CLIENT INTERACTIVITY & CONTROLLER
// Real-time Chat, Closed-Loop Evaluator, and EHR Explorer
// =====================================================================

document.addEventListener('DOMContentLoaded', () => {
  // DOM Elements - Navigation
  const tabBtns = document.querySelectorAll('.tab-btn');
  const tabPanes = document.querySelectorAll('.tab-pane');
  const btnReset = document.getElementById('btn-reset-system');
  const modelNameBadge = document.getElementById('model-name');

  // DOM Elements - Live Chat & State
  const chatForm = document.getElementById('chat-form');
  const chatInput = document.getElementById('chat-input');
  const chatMessages = document.getElementById('chat-messages');
  const promptChips = document.querySelectorAll('.prompt-chip');

  const statePatientId = document.getElementById('state-patient-id');
  const badgeIdentityVerified = document.getElementById('badge-identity-verified');
  const badgeEmergencyStatus = document.getElementById('badge-emergency-status');
  const badgeConfirmationStatus = document.getElementById('badge-confirmation-status');
  const stateHoldId = document.getElementById('state-hold-id');
  const stateAppointmentId = document.getElementById('state-appointment-id');
  const stateLastTool = document.getElementById('state-last-tool');
  const turnBadge = document.getElementById('turn-badge');

  const triageStatusDot = document.getElementById('triage-status-dot');
  const triagePolicyTitle = document.getElementById('triage-policy-title');
  const triagePolicyDesc = document.getElementById('triage-policy-desc');

  // DOM Elements - Closed-Loop Evaluator
  const btnRunEval = document.getElementById('btn-run-eval');
  const evalLoading = document.getElementById('eval-loading');
  const evalStepDesc = document.getElementById('eval-step-desc');
  const evalResults = document.getElementById('eval-results');
  const verdictBanner = document.getElementById('verdict-banner');
  const verdictIcon = document.getElementById('verdict-icon');
  const verdictTitle = document.getElementById('verdict-title');
  const verdictDesc = document.getElementById('verdict-desc');
  const statScoreDelta = document.getElementById('stat-score-delta');
  const statRegressions = document.getElementById('stat-regressions');
  const comparisonTableBody = document.getElementById('comparison-table-body');
  const failJsonBox = document.getElementById('fail-json-box');
  const failSeverity = document.getElementById('fail-severity');
  const patchJsonBox = document.getElementById('patch-json-box');

  // DOM Elements - EHR Tables
  const tableProviders = document.querySelector('#table-providers tbody');
  const tablePatients = document.querySelector('#table-patients tbody');
  const tableSlots = document.querySelector('#table-slots tbody');
  const tableAppointments = document.querySelector('#table-appointments tbody');
  const tableAudit = document.querySelector('#table-audit tbody');

  let currentTurn = 0;

  // -------------------------------------------------------------------
  // 1. Tab Navigation Handling
  // -------------------------------------------------------------------
  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      tabBtns.forEach(b => b.classList.remove('active'));
      tabPanes.forEach(p => p.classList.remove('active'));

      btn.classList.add('active');
      const targetTab = document.getElementById(btn.dataset.tab);
      if (targetTab) {
        targetTab.classList.add('active');
      }

      if (btn.dataset.tab === 'ehr-tab') {
        fetchEhrData();
      }
    });
  });

  // -------------------------------------------------------------------
  // 2. Health & State Synchronization
  // -------------------------------------------------------------------
  async function checkHealthAndState() {
    try {
      const healthRes = await fetch('/api/health');
      if (healthRes.ok) {
        const health = await healthRes.json();
        if (health.model && health.model !== 'NOT_CONFIGURED') {
          modelNameBadge.textContent = health.model;
        }
      }

      await refreshState();
      await refreshPolicies();
    } catch (err) {
      console.warn('System status fetch failed:', err);
    }
  }

  async function refreshState() {
    try {
      const res = await fetch('/api/state');
      if (!res.ok) return;
      const data = await res.json();
      updateStateSidebar(data.state);
    } catch (err) {
      console.warn('Failed to refresh state:', err);
    }
  }

  async function refreshPolicies() {
    try {
      const res = await fetch('/api/policies');
      if (!res.ok) return;
      const data = await res.json();
      const triage = data.tunable_policies?.triage_screening;

      if (triage && triage.enabled) {
        triageStatusDot.className = 'guardrail-dot green';
        triagePolicyTitle.textContent = 'Tunable: Pre-Tool Triage Screening (Active)';
        triagePolicyDesc.textContent = `Enforcing acute chest pain/dyspnea screening before slots. Severity threshold: ${triage.severity_threshold || 'HIGH'}`;
      } else {
        triageStatusDot.className = 'guardrail-dot amber';
        triagePolicyTitle.textContent = 'Tunable: Pre-Tool Triage Screening (Baseline: Inactive)';
        triagePolicyDesc.textContent = 'Baseline mode: Emergency routing relies on core prompt. Closed loop will synthesize reinforcement.';
      }
    } catch (err) {
      console.warn('Failed to refresh policies:', err);
    }
  }

  function updateStateSidebar(state) {
    if (!state) return;

    statePatientId.textContent = state.patient_name ? `${state.patient_name} (${state.patient_id})` : (state.patient_id || 'Unverified');

    if (state.identity_verified) {
      badgeIdentityVerified.className = 'state-badge badge-verified';
      badgeIdentityVerified.textContent = 'VERIFIED';
    } else {
      badgeIdentityVerified.className = 'state-badge badge-unverified';
      badgeIdentityVerified.textContent = 'UNVERIFIED';
    }

    if (state.emergency_status === 'EMERGENCY' || state.emergency_status === 'ESCALATED') {
      badgeEmergencyStatus.className = 'state-badge badge-danger';
      badgeEmergencyStatus.textContent = '🚨 EMERGENCY';
    } else if (state.emergency_status === 'URGENT') {
      badgeEmergencyStatus.className = 'state-badge badge-pending';
      badgeEmergencyStatus.textContent = 'URGENT';
    } else {
      badgeEmergencyStatus.className = 'state-badge badge-safe';
      badgeEmergencyStatus.textContent = 'ROUTINE';
    }

    badgeConfirmationStatus.textContent = state.confirmation_status || 'PENDING';
    if (state.confirmation_status === 'CONFIRMED') {
      badgeConfirmationStatus.className = 'state-badge badge-verified';
    } else {
      badgeConfirmationStatus.className = 'state-badge badge-pending';
    }

    if (state.hold_id || state.active_hold_id) {
      stateHoldId.className = 'state-value code-value';
      stateHoldId.textContent = state.hold_id || state.active_hold_id;
    } else {
      stateHoldId.className = 'state-value empty-val';
      stateHoldId.textContent = 'No active hold';
    }

    if (state.appointment_id || state.confirmed_appointment_id) {
      stateAppointmentId.className = 'state-value code-value';
      stateAppointmentId.textContent = state.appointment_id || state.confirmed_appointment_id;
    } else {
      stateAppointmentId.className = 'state-value empty-val';
      stateAppointmentId.textContent = 'No confirmed booking';
    }

    if (state.last_tool_call) {
      stateLastTool.className = 'state-value tool-tag';
      const resultTxt = state.last_tool_result ? JSON.stringify(state.last_tool_result).slice(0, 45) + '...' : '';
      stateLastTool.textContent = `${state.last_tool_call} (${resultTxt || 'done'})`;
    } else {
      stateLastTool.className = 'state-value empty-val';
      stateLastTool.textContent = 'Awaiting action';
    }
  }

  // -------------------------------------------------------------------
  // 3. Live Chat Handling
  // -------------------------------------------------------------------
  chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = chatInput.value.trim();
    if (!text) return;

    chatInput.value = '';
    currentTurn += 1;
    turnBadge.textContent = `Turn ${currentTurn}`;

    // Append user message bubble
    appendMessage('user', text);

    // Show typing bubble
    const typingBubble = appendTypingIndicator();

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text })
      });

      typingBubble.remove();

      if (!res.ok) {
        const errorData = await res.json();
        appendMessage('agent', `⚠️ Error: ${errorData.detail || 'Failed to process message'}`);
        return;
      }

      const data = await res.json();
      appendMessage('agent', data.reply, data.last_tool, data.last_tool_result);
      updateStateSidebar(data.state);
      await refreshPolicies();
    } catch (err) {
      typingBubble.remove();
      appendMessage('agent', `⚠️ Network error: ${err.message}`);
    }
  });

  // Prompt chips
  promptChips.forEach(chip => {
    chip.addEventListener('click', () => {
      chatInput.value = chip.dataset.prompt;
      chatInput.focus();
    });
  });

  function appendMessage(role, text, toolCall = null, toolResult = null) {
    const bubble = document.createElement('div');
    bubble.className = `message-bubble ${role === 'user' ? 'user-message' : 'agent-message'}`;

    const avatar = document.createElement('div');
    avatar.className = 'msg-avatar';
    avatar.textContent = role === 'user' ? '👤' : '🤖';

    const content = document.createElement('div');
    content.className = 'msg-content';

    const author = document.createElement('div');
    author.className = 'msg-author';
    author.textContent = role === 'user' ? 'Patient' : 'Clinical Scheduling Assistant';

    const p = document.createElement('p');
    p.textContent = text;

    content.appendChild(author);
    content.appendChild(p);

    if (toolCall) {
      const toolBadge = document.createElement('div');
      const isError = toolResult && toolResult.status === 'ERROR';
      toolBadge.className = `tool-badge-pill ${isError ? 'status-error' : ''}`;
      toolBadge.innerHTML = `⚙️ Tool: <strong>${escapeHtml(toolCall)}</strong> &rarr; ${isError ? 'FAIL' : 'SUCCESS'}`;
      content.appendChild(toolBadge);
    }

    bubble.appendChild(avatar);
    bubble.appendChild(content);

    chatMessages.appendChild(bubble);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function appendTypingIndicator() {
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble agent-message';

    const avatar = document.createElement('div');
    avatar.className = 'msg-avatar';
    avatar.textContent = '🤖';

    const content = document.createElement('div');
    content.className = 'msg-content typing-bubble';
    content.innerHTML = `
      <span class="typing-dot"></span>
      <span class="typing-dot"></span>
      <span class="typing-dot"></span>
    `;

    bubble.appendChild(avatar);
    bubble.appendChild(content);
    chatMessages.appendChild(bubble);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    return bubble;
  }

  // -------------------------------------------------------------------
  // 4. Reset System Button
  // -------------------------------------------------------------------
  btnReset.addEventListener('click', async () => {
    if (!confirm('Are you sure you want to reset the EHR database and agent state to the clean baseline?')) {
      return;
    }

    try {
      const res = await fetch('/api/reset', { method: 'POST' });
      if (res.ok) {
        currentTurn = 0;
        turnBadge.textContent = 'Turn 0';
        chatMessages.innerHTML = `
          <div class="message-bubble agent-message">
            <div class="msg-avatar">🤖</div>
            <div class="msg-content">
              <div class="msg-author">Clinical Scheduling Assistant</div>
              <p>System reset complete. Welcome to Aegis Clinic. How can I help you schedule with Cardiology, Primary Care, or Orthopedics?</p>
            </div>
          </div>
        `;
        await refreshState();
        await refreshPolicies();
        if (document.getElementById('ehr-tab').classList.contains('active')) {
          await fetchEhrData();
        }
      }
    } catch (err) {
      alert(`Reset failed: ${err.message}`);
    }
  });

  // -------------------------------------------------------------------
  // 5. Closed-Loop Optimization & Evaluation Runner
  // -------------------------------------------------------------------
  btnRunEval.addEventListener('click', async () => {
    btnRunEval.disabled = true;
    evalResults.style.display = 'none';
    evalLoading.style.display = 'flex';

    // Simulated progress steps for visual feedback
    const steps = [
      'Running Baseline Evaluation (Scenarios S1 - S8)...',
      'Evaluating Programmatic Invariants & Dual EHR State Grounding...',
      'Synthesizing Structured FailureReport on Acute Emergency Triage...',
      'Root Cause Diagnosis: Activating Pre-Tool Triage Screening Policy...',
      'Validating Candidate PolicyPatch against Schema and Immutability Matrix...',
      'Executing Shadow Benchmark Run with Policy Injected...',
      'Auditing for Regressions Across All 8 Benchmark Scenarios...'
    ];

    let stepIdx = 0;
    const interval = setInterval(() => {
      stepIdx = (stepIdx + 1) % steps.length;
      evalStepDesc.textContent = steps[stepIdx];
    }, 4500);

    try {
      const res = await fetch('/api/eval/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });

      clearInterval(interval);
      evalLoading.style.display = 'none';
      btnRunEval.disabled = false;

      if (!res.ok) {
        const errData = await res.json();
        alert(`Evaluation failed: ${errData.detail || 'Unknown server error'}`);
        return;
      }

      const result = await res.json();
      renderEvalResults(result);
      await refreshPolicies();
    } catch (err) {
      clearInterval(interval);
      evalLoading.style.display = 'none';
      btnRunEval.disabled = false;
      alert(`Evaluation error: ${err.message}`);
    }
  });

  function renderEvalResults(result) {
    evalResults.style.display = 'block';

    const isAccepted = result.decision === 'ACCEPTED';
    if (isAccepted) {
      verdictBanner.className = 'verdict-banner glass-panel';
      verdictIcon.textContent = '✓';
      verdictTitle.textContent = 'POLICY PATCH ACCEPTED';
      verdictDesc.textContent = result.decision_reason || 'Candidate patch resolved emergency triage failure with zero regressions.';
    } else {
      verdictBanner.className = 'verdict-banner rejected glass-panel';
      verdictIcon.textContent = '✕';
      verdictTitle.textContent = 'POLICY PATCH REJECTED';
      verdictDesc.textContent = result.decision_reason || 'Candidate patch failed acceptance criteria.';
    }

    const sign = result.score_delta >= 0 ? '+' : '';
    statScoreDelta.textContent = `${sign}${Number(result.score_delta).toFixed(1)}%`;
    statRegressions.textContent = (result.regressions || []).length.toString();

    // Populate Comparison Matrix
    comparisonTableBody.innerHTML = '';

    const baselineResults = {};
    (result.baseline_summary?.results || []).forEach(r => {
      baselineResults[r.scenario_id] = r;
    });

    const shadowResults = {};
    (result.shadow_summary?.results || []).forEach(r => {
      shadowResults[r.scenario_id] = r;
    });

    const allScenarioIds = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8'];

    allScenarioIds.forEach(scId => {
      const bRes = baselineResults[scId];
      const sRes = shadowResults[scId];

      const scName = sRes?.scenario_name || bRes?.scenario_name || `Scenario ${scId}`;

      const bScore = bRes ? `${bRes.final_score.toFixed(1)}%` : 'N/A';
      const sScore = sRes ? `${sRes.final_score.toFixed(1)}%` : 'N/A';

      const bVal = bRes ? bRes.final_score : 0;
      const sVal = sRes ? sRes.final_score : 0;
      const delta = sVal - bVal;

      let deltaClass = 'delta-neutral';
      let deltaStr = '0.0%';
      if (delta > 0.1) {
        deltaClass = 'delta-pos';
        deltaStr = `+${delta.toFixed(1)}%`;
      } else if (delta < -0.1) {
        deltaClass = 'delta-neg';
        deltaStr = `${delta.toFixed(1)}%`;
      }

      const tr = document.createElement('tr');

      const safetyGatePassed = sRes ? sRes.invariants.every(inv => inv.passed) : false;
      const isRegressed = result.regressions && result.regressions.includes(scId);

      tr.innerHTML = `
        <td><strong>${escapeHtml(scId)}: ${escapeHtml(scName)}</strong></td>
        <td>${bScore}</td>
        <td><strong>${sScore}</strong></td>
        <td class="${deltaClass}">${deltaStr}</td>
        <td>
          <span class="pill-badge ${safetyGatePassed ? 'green-badge' : 'red-badge'}">
            ${safetyGatePassed ? 'PASSED' : 'VIOLATED'}
          </span>
        </td>
        <td>
          <span class="pill-badge ${isRegressed ? 'red-badge' : 'green-badge'}">
            ${isRegressed ? 'REGRESSED' : '0 REGRESSION'}
          </span>
        </td>
      `;

      comparisonTableBody.appendChild(tr);
    });

    // Populate Failure Report Box
    const targetReport = (result.baseline_summary?.failure_reports || []).find(f => f.scenario_id === result.target_scenario_id) || (result.baseline_summary?.failure_reports || [])[0];
    if (targetReport) {
      failJsonBox.textContent = JSON.stringify(targetReport, null, 2);
      failSeverity.textContent = targetReport.severity || 'CRITICAL';
    } else {
      failJsonBox.textContent = JSON.stringify({
        status: "OPTIMIZED",
        message: "No failures detected. All 8 benchmark scenarios meeting clinical safety invariants."
      }, null, 2);
      failSeverity.textContent = 'NONE';
    }

    // Populate Candidate Patch Box
    if (result.candidate_patch) {
      patchJsonBox.textContent = JSON.stringify(result.candidate_patch, null, 2);
    } else {
      patchJsonBox.textContent = JSON.stringify({ message: "No patch required." }, null, 2);
    }
  }

  // -------------------------------------------------------------------
  // 6. Clinic EHR Database & Audit Explorer
  // -------------------------------------------------------------------
  async function fetchEhrData() {
    try {
      const res = await fetch('/api/ehr');
      if (!res.ok) return;
      const data = await res.json();

      // Build Provider & Patient lookup maps for clean display
      const providerMap = {};
      (data.providers || []).forEach(p => {
        providerMap[p.id] = p.name;
      });

      const patientMap = {};
      (data.patients || []).forEach(pat => {
        const name = (pat.first_name && pat.last_name) ? `${pat.first_name} ${pat.last_name}` : (pat.name || pat.id);
        patientMap[pat.id] = name;
      });

      // Render Providers
      tableProviders.innerHTML = '';
      (data.providers || []).forEach(p => {
        const tr = document.createElement('tr');
        const loc = p.clinic_location || p.location || 'Heart Health Pavilion';
        tr.innerHTML = `
          <td><code>${escapeHtml(p.id)}</code></td>
          <td><strong>${escapeHtml(p.name)}</strong></td>
          <td><span class="pill-badge blue-badge">${escapeHtml(p.specialty)}</span></td>
          <td>${escapeHtml(loc)}</td>
        `;
        tableProviders.appendChild(tr);
      });

      // Render Patients
      tablePatients.innerHTML = '';
      (data.patients || []).forEach(pat => {
        const tr = document.createElement('tr');
        const fullName = (pat.first_name && pat.last_name) ? `${pat.first_name} ${pat.last_name}` : (pat.name || 'Anonymous');
        const notes = pat.existing_notes || pat.notes || 'Routine care';
        tr.innerHTML = `
          <td><code>${escapeHtml(pat.id)}</code></td>
          <td><strong>${escapeHtml(fullName)}</strong></td>
          <td>${escapeHtml(pat.dob || '-')}</td>
          <td>${escapeHtml(pat.phone || '-')}</td>
          <td><small>${escapeHtml(notes)}</small></td>
        `;
        tablePatients.appendChild(tr);
      });

      // Render Slots
      tableSlots.innerHTML = '';
      (data.slots || []).forEach(s => {
        const tr = document.createElement('tr');
        let statusBadge = 'blue-badge';
        if (s.status === 'AVAILABLE') statusBadge = 'green-badge';
        else if (s.status === 'BOOKED') statusBadge = 'red-badge';
        else if (s.status === 'HELD') statusBadge = 'amber-badge';

        const provName = providerMap[s.provider_id] ? `${providerMap[s.provider_id]} (${s.provider_id})` : s.provider_id;

        // Safe time display
        let formattedTime = s.start_time;
        try {
          const iso = s.start_time.includes('T') ? s.start_time : s.start_time.replace(' ', 'T');
          const d = new Date(iso);
          if (!isNaN(d.getTime())) {
            formattedTime = d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
          }
        } catch (_) {}

        tr.innerHTML = `
          <td><code>${escapeHtml(s.id)}</code></td>
          <td>${escapeHtml(provName)}</td>
          <td>${escapeHtml(formattedTime)}</td>
          <td><span class="pill-badge ${statusBadge}">${escapeHtml(s.status)}</span></td>
        `;
        tableSlots.appendChild(tr);
      });

      // Render Appointments
      tableAppointments.innerHTML = '';
      if (!data.appointments || data.appointments.length === 0) {
        tableAppointments.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No confirmed bookings yet.</td></tr>';
      } else {
        data.appointments.forEach(a => {
          const tr = document.createElement('tr');
          const patLabel = patientMap[a.patient_id] ? `${patientMap[a.patient_id]} (${a.patient_id})` : a.patient_id;
          const statusClass = a.status === 'CONFIRMED' ? 'green-badge' : (a.status === 'CANCELLED' ? 'red-badge' : 'blue-badge');
          tr.innerHTML = `
            <td><code>${escapeHtml(a.id)}</code></td>
            <td><strong>${escapeHtml(patLabel)}</strong></td>
            <td><code>${escapeHtml(a.slot_id)}</code></td>
            <td>${escapeHtml(a.reason || 'Consultation')}</td>
            <td><span class="pill-badge ${statusClass}">${escapeHtml(a.status)}</span></td>
          `;
          tableAppointments.appendChild(tr);
        });
      }

      // Render Audit Trail
      tableAudit.innerHTML = '';
      (data.audit_log || []).forEach(log => {
        const tr = document.createElement('tr');
        const isSuccess = log.success === true || log.status === 'SUCCESS';
        const statusLabel = isSuccess ? 'SUCCESS' : 'FAILED';
        const patLabel = log.patient_id ? (patientMap[log.patient_id] ? `${patientMap[log.patient_id]} (${log.patient_id})` : log.patient_id) : 'System / Pre-Auth';
        const paramStr = JSON.stringify({ params: log.parameters, result: log.result }).slice(0, 75);

        // Safe time display
        let formattedTime = log.timestamp;
        try {
          const iso = log.timestamp.includes('T') ? log.timestamp : log.timestamp.replace(' ', 'T');
          const d = new Date(iso);
          if (!isNaN(d.getTime())) formattedTime = d.toLocaleTimeString();
        } catch (_) {}

        tr.innerHTML = `
          <td><small>${escapeHtml(formattedTime)}</small></td>
          <td><strong>${escapeHtml(log.tool_name)}</strong></td>
          <td><code>${escapeHtml(patLabel)}</code></td>
          <td>
            <span class="pill-badge ${isSuccess ? 'green-badge' : 'red-badge'}">
              ${statusLabel}
            </span>
          </td>
          <td><code style="font-size: 0.72rem;">${escapeHtml(paramStr)}...</code></td>
        `;
        tableAudit.appendChild(tr);
      });

    } catch (err) {
      console.warn('EHR fetch error:', err);
    }
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // Initial Load
  checkHealthAndState();
});
