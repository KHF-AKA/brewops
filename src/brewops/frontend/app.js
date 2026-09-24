// BrewOps frontend — vanilla JS, no dependencies, no build step.

async function fetchJSON(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `${response.status} ${response.statusText}`);
  }
  return response.json();
}

// ---- dashboard ----

function renderDrinkBars(perDrink) {
  const container = document.getElementById("drink-bars");
  container.innerHTML = "";
  const max = Math.max(1, ...perDrink.map((d) => d.count));
  for (const drink of perDrink) {
    const row = document.createElement("div");
    row.className = "bar-row";
    row.innerHTML = `
      <span class="bar-label">${drink.label}</span>
      <span class="bar-track"><span class="bar-fill" style="width:${(drink.count / max) * 100}%"></span></span>
      <span class="bar-count">${drink.count}</span>`;
    container.appendChild(row);
  }
}

function renderTimeline(perDay) {
  const svg = document.getElementById("timeline");
  svg.innerHTML = "";
  if (perDay.length === 0) return;
  const width = 600;
  const height = 130;
  const max = Math.max(...perDay.map((d) => d.count));
  const barWidth = width / perDay.length;
  perDay.forEach((day, i) => {
    const barHeight = (day.count / max) * (height - 10);
    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    rect.setAttribute("x", i * barWidth);
    rect.setAttribute("y", height - barHeight);
    rect.setAttribute("width", Math.max(0.5, barWidth - 0.6));
    rect.setAttribute("height", barHeight);
    rect.setAttribute("class", "timeline-bar");
    const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
    title.textContent = `${day.day}: ${day.count} brews`;
    rect.appendChild(title);
    svg.appendChild(rect);
  });
}

function renderUsageHistogram(usageByWeekday, machineName) {
  const width = 182;
  const barsHeight = 36;
  const height = 54;
  const slotWidth = width / usageByWeekday.length;
  const barWidth = Math.max(0.5, slotWidth - 6);
  const max = Math.max(1, ...usageByWeekday.map((d) => d.count));
  const bars = usageByWeekday
    .map((d, i) => {
      const barHeight = Math.max(2, (d.count / max) * barsHeight);
      const x = i * slotWidth + (slotWidth - barWidth) / 2;
      const y = barsHeight - barHeight;
      const labelX = i * slotWidth + slotWidth / 2;
      const brewWord = d.count === 1 ? "brew" : "brews";
      return `
        <rect class="timeline-bar" x="${x}" y="${y}" width="${barWidth}" height="${barHeight}">
          <title>${d.weekday}: ${d.count} ${brewWord}</title>
        </rect>
        <text class="usage-label" x="${labelX}" y="${height - 2}" text-anchor="middle">${d.weekday[0]}</text>`;
    })
    .join("");
  return `
    <svg class="usage-histogram" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none"
         role="img" aria-label="Brews by day of week for ${machineName}">${bars}</svg>`;
}

function renderMachineCards(healths) {
  const container = document.getElementById("machine-cards");
  container.innerHTML = "";
  for (const m of healths) {
    const card = document.createElement("div");
    card.className = "card";
    const specialty = m.specialty ? `${m.specialty.label} (${m.specialty.count})` : "no brews yet";
    card.innerHTML = `
      <h3>${m.name}</h3>
      <p class="badge">${m.has_telemetry ? "telemetry" : "manual log"}</p>
      <p>${m.brew_count} brews · last ${m.last_brew ? m.last_brew.slice(0, 16) : "never"}</p>
      <p>Specialty: ${specialty}</p>
      <p class="usage-caption">Load by weekday</p>
      ${renderUsageHistogram(m.usage_by_weekday, m.name)}`;
    container.appendChild(card);
  }
}

function rangeQS() {
  const start = document.getElementById("dash-start").value;
  const end = document.getElementById("dash-end").value;
  const params = new URLSearchParams();
  if (start) params.set("start", start);
  if (end) params.set("end", end);
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

async function loadDashboard() {
  const qs = rangeQS();
  const stats = await fetchJSON(`/api/stats${qs}`);
  document.getElementById("total-brews").textContent = stats.total_brews;
  const lastDay = stats.per_day[stats.per_day.length - 1];
  document.getElementById("brews-today").textContent = lastDay ? lastDay.count : 0;

  const label = document.getElementById("brews-today-label");
  if (qs) {
    label.textContent = "Last day in range";
  } else {
    label.textContent = "brews on last active day";
  }

  renderDrinkBars(stats.per_drink);
  renderTimeline(stats.per_day);

  const machines = await fetchJSON("/api/machines");
  document.getElementById("machine-count").textContent = machines.length;
  const healths = await Promise.all(machines.map((m) => fetchJSON(`/api/machines/${m.id}${qs}`)));
  renderMachineCards(healths);
}

function initRangeFromURL() {
  const params = new URLSearchParams(location.search);
  const start = params.get("start");
  const end = params.get("end");
  if (start) document.getElementById("dash-start").value = start;
  if (end) document.getElementById("dash-end").value = end;
}

function onRangeChange() {
  const qs = rangeQS();
  const url = qs ? `?${qs}` : location.pathname;
  history.replaceState(null, "", url);
  loadDashboard().catch((error) => {
    console.error("Dashboard reload failed:", error);
  });
}

// ---- forms ----

function localNow() {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 16); // datetime-local format
}

function fillSelect(select, items, valueKey, labelKey) {
  select.innerHTML = "";
  for (const item of items) {
    const option = document.createElement("option");
    option.value = item[valueKey];
    option.textContent = item[labelKey];
    select.appendChild(option);
  }
}

async function setupForms() {
  const machines = await fetchJSON("/api/machines");
  const drinks = await fetchJSON("/api/drink-types");
  fillSelect(document.getElementById("brew-machine"), machines, "id", "name");
  fillSelect(document.getElementById("brew-drink"), drinks, "name", "label");
  fillSelect(document.getElementById("maintenance-machine"), machines, "id", "name");
  document.getElementById("brew-timestamp").value = localNow();
  document.getElementById("maintenance-timestamp").value = localNow();

  document.getElementById("brew-form").addEventListener("submit", (event) =>
    submitForm(event, "/api/brews", "brew-message", () => ({
      machine_id: Number(document.getElementById("brew-machine").value),
      drink_type: document.getElementById("brew-drink").value,
      timestamp: document.getElementById("brew-timestamp").value,
    }))
  );

  document.getElementById("maintenance-form").addEventListener("submit", (event) =>
    submitForm(event, "/api/maintenance", "maintenance-message", () => ({
      machine_id: Number(document.getElementById("maintenance-machine").value),
      type: document.getElementById("maintenance-type").value,
      timestamp: document.getElementById("maintenance-timestamp").value,
      note: document.getElementById("maintenance-note").value || null,
    }))
  );
}

async function submitForm(event, url, messageId, buildPayload) {
  event.preventDefault();
  const message = document.getElementById(messageId);
  message.textContent = "";
  message.className = "message";
  try {
    await fetchJSON(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildPayload()),
    });
    message.textContent = "Logged.";
    message.classList.add("ok");
    await loadDashboard();
  } catch (error) {
    message.textContent = error.message;
    message.classList.add("error");
  }
}

initRangeFromURL();
document.getElementById("dash-start").addEventListener("change", onRangeChange);
document.getElementById("dash-end").addEventListener("change", onRangeChange);
document.getElementById("dash-clear").addEventListener("click", () => {
  document.getElementById("dash-start").value = "";
  document.getElementById("dash-end").value = "";
  onRangeChange();
});

loadDashboard().catch((error) => {
  document.getElementById("total-brews").textContent = "!";
  console.error("Dashboard failed to load:", error);
});
setupForms().catch((error) => console.error("Form setup failed:", error));
