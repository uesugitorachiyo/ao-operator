const state = {
  requests: [],
  selectedId: null,
};

const statusOrder = ["new", "follow-up", "scheduled", "lost"];

function money(value) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

function buildNextAction(request) {
  if (request.urgency === "High") {
    return `Call ${request.customer} now about ${request.service}. Offer the soonest ${request.window} slot and hold it for 15 minutes.`;
  }
  if (request.urgency === "Medium") {
    return `Send ${request.customer} two appointment options for ${request.service} during ${request.window}.`;
  }
  return `Ask ${request.customer} for preferred dates for ${request.service}, then add the best option to the schedule.`;
}

async function loadSeed() {
  const response = await fetch("./data/seed-requests.json", { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Seed data failed to load: ${response.status}`);
  }
  state.requests = await response.json();
  state.selectedId = state.requests[0]?.id ?? null;
  render();
}

function updateMetrics() {
  const urgent = state.requests.filter((request) => request.urgency === "High").length;
  const scheduled = state.requests.filter((request) => request.status === "scheduled").length;
  const saveable = state.requests
    .filter((request) => request.status !== "lost")
    .reduce((sum, request) => sum + Number(request.estimate), 0);
  document.querySelector("#totalRequests").textContent = state.requests.length;
  document.querySelector("#urgentRequests").textContent = urgent;
  document.querySelector("#scheduledRequests").textContent = scheduled;
  document.querySelector("#saveableRevenue").textContent = money(saveable);
}

function renderColumns() {
  const container = document.querySelector("#columns");
  container.innerHTML = "";
  for (const status of statusOrder) {
    const requests = state.requests.filter((request) => request.status === status);
    const column = document.createElement("section");
    column.className = "column";
    column.innerHTML = `<h3>${status}<span>${requests.length}</span></h3>`;
    for (const request of requests) {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "request-card";
      card.setAttribute("aria-selected", String(request.id === state.selectedId));
      card.innerHTML = `<strong>${request.customer}</strong><small>${request.service} - ${request.window} - ${money(request.estimate)}</small>`;
      card.addEventListener("click", () => {
        state.selectedId = request.id;
        render();
      });
      column.appendChild(card);
    }
    container.appendChild(column);
  }
}

function renderSelected() {
  const request = state.requests.find((item) => item.id === state.selectedId);
  const action = document.querySelector("#nextAction");
  if (!request) {
    document.querySelector("#selectedCustomer").textContent = "Select a request";
    document.querySelector("#selectedMeta").textContent = "No request selected.";
    action.value = "";
    return;
  }
  document.querySelector("#selectedCustomer").textContent = request.customer;
  document.querySelector("#selectedMeta").textContent = `${request.service} - ${request.urgency} urgency - ${money(request.estimate)}`;
  action.value = request.nextAction;
}

function addRequest(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  const request = {
    id: `req-${Date.now()}`,
    customer: String(data.get("customer")),
    service: String(data.get("service")),
    window: String(data.get("window")),
    urgency: String(data.get("urgency")),
    status: "new",
    estimate: Number(data.get("estimate") || 0),
    nextAction: "",
  };
  request.nextAction = buildNextAction(request);
  state.requests.unshift(request);
  state.selectedId = request.id;
  render();
}

function render() {
  updateMetrics();
  renderColumns();
  renderSelected();
}

document.querySelector("#requestForm").addEventListener("submit", addRequest);
loadSeed();
