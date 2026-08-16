"use client";

import { BarChart3, CheckSquare, Copy, Download, Edit3, ListFilter, LogOut, Menu, Mic, PanelLeftClose, PanelLeftOpen, RefreshCw, Save, Search, Table2, Ticket, Trash2, Users, X } from "lucide-react";
import { Fragment, FormEvent, useEffect, useMemo, useState } from "react";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Section = "activities" | "statistics" | "overhead" | "users";
type SummaryGroup = "day" | "week" | "month" | "year";

type ProjectRow = {
  project_name: string;
  hours: string;
};

type PeriodRow = {
  period_key: string;
  period_label: string;
  date_from: string;
  date_to: string;
  hours: string;
};

type StatsPeriodRow = PeriodRow & {
  level: "month" | "quarter" | "year" | "total";
};

type CategoryPeriodRow = {
  period_key: string;
  period_label: string;
  date_from: string;
  date_to: string;
  abra_hours: string;
  education_hours: string;
  private_hours: string;
  tanaka_hours: string;
  total_hours: string;
};

type CategoryComparisonRow = {
  category_key: string;
  label: string;
  current_week_hours: string;
  previous_week_hours: string;
  week_delta_hours: string;
  current_month_hours: string;
  previous_month_same_period_hours: string;
  month_delta_hours: string;
};

type CategoryComparison = {
  today: string;
  current_week_from: string;
  current_week_to: string;
  previous_week_from: string;
  previous_week_to: string;
  current_month_from: string;
  current_month_to: string;
  previous_month_from: string;
  previous_month_to: string;
  rows: CategoryComparisonRow[];
};

type ActivityRow = {
  id: string;
  spent_on: string;
  started_at: string | null;
  ended_at: string | null;
  duration_hours: string;
  overlap_hours: string | null;
  effective_hours: string;
  category_code: string | null;
  description: string;
  ticket_external_id: string | null;
  project_name: string | null;
  transport_name: string | null;
  km: string | null;
  reported_status: string | null;
};

type OverheadTicket = {
  external_id: string;
  project_name: string | null;
  subject: string | null;
  source_period: string | null;
  valid_from: string | null;
  valid_to: string | null;
};

type CurrentUser = {
  username: string;
  role: string;
};

type UserRow = {
  username: string;
  role: string;
  is_active: boolean;
};

type UserDraft = {
  username: string;
  password: string;
  role: string;
  is_active: boolean;
};

type EntryDraft = {
  spent_on: string;
  started_at: string;
  ended_at: string;
  duration_hours: string;
  category_code: string;
  description: string;
  ticket_external_id: string;
  project_name: string;
  transport_name: string;
  km: string;
  reported_status: string;
  raw_text?: string;
};

type Filters = {
  date_from: string;
  date_to: string;
  project: string;
  ticket: string;
  text: string;
};

const today = () => new Date().toISOString().slice(0, 10);

const emptyDraft: EntryDraft = {
  spent_on: today(),
  started_at: "",
  ended_at: "",
  duration_hours: "0.25",
  category_code: "",
  description: "",
  ticket_external_id: "",
  project_name: "",
  transport_name: "",
  km: "",
  reported_status: ""
};

const transportOptions = ["Volvo XC90", "vlak", "autobus", "MHD"];

const defaultFilters: Filters = {
  date_from: "",
  date_to: "",
  project: "",
  ticket: "",
  text: ""
};

const categorySeries = [
  { key: "abra_hours", label: "ABRA", color: "#15616d" },
  { key: "education_hours", label: "Vzdelavani", color: "#6b5b95" },
  { key: "private_hours", label: "Soukrome", color: "#c17c1f" },
  { key: "tanaka_hours", label: "TANAKA", color: "#3f5f8f" }
] as const;

const sections: { id: Section; label: string; icon: typeof Table2; adminOnly?: boolean }[] = [
  { id: "activities", label: "Aktivity", icon: Table2 },
  { id: "statistics", label: "Statistiky", icon: BarChart3 },
  { id: "overhead", label: "Rezijni tikety", icon: Ticket },
  { id: "users", label: "Uzivatele", icon: Users, adminOnly: true }
];

const emptyUserDraft: UserDraft = {
  username: "",
  password: "",
  role: "viewer",
  is_active: true
};

function timeValue(value: string | null) {
  return value ? value.slice(0, 5) : "";
}

function formatDateTime(value: string | null) {
  if (!value) {
    return "";
  }
  return value.replace("T", " ").slice(0, 16);
}

function formatKm(value: string | null) {
  if (!value) {
    return "";
  }
  return Math.round(Number(value)).toString();
}

function weekdayName(value: string) {
  const names = ["Ne", "Po", "Ut", "St", "Ct", "Pa", "So"];
  const date = new Date(`${value}T12:00:00`);
  return names[date.getDay()] ?? "";
}

function buildQuery(params: Record<string, string>) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value) {
      query.set(key, value);
    }
  });
  return query.toString();
}

function inferredCategory(projectName: string) {
  const normalized = projectName
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
  if (normalized === "abra vr") return "A";
  if (normalized === "anglictina") return "V";
  if (normalized === "rd kvasice" || normalized === "investice") return "S";
  return "";
}

function addHours(left: string, right: string) {
  return (Number(left || 0) + Number(right || 0)).toFixed(2);
}

function quarterLabel(monthKey: string) {
  const [year, monthText] = monthKey.split("-");
  const quarter = Math.ceil(Number(monthText) / 3);
  return `${year}-Q${quarter}`;
}

function buildStatsRows(months: PeriodRow[]): StatsPeriodRow[] {
  const rows: StatsPeriodRow[] = [];
  const quarters = new Map<string, StatsPeriodRow>();
  const years = new Map<string, StatsPeriodRow>();
  let total: StatsPeriodRow | null = null;

  for (let index = 0; index < months.length; index += 1) {
    const month = months[index];
    const monthRow: StatsPeriodRow = { ...month, level: "month" };
    rows.push(monthRow);

    const quarterKey = quarterLabel(month.period_key);
    const quarterRow = quarters.get(quarterKey) ?? {
      period_key: quarterKey,
      period_label: `Soucet ${quarterKey}`,
      date_from: month.date_from,
      date_to: month.date_to,
      hours: "0.00",
      level: "quarter" as const
    };
    quarterRow.date_to = month.date_to;
    quarterRow.hours = addHours(quarterRow.hours, month.hours);
    quarters.set(quarterKey, quarterRow);

    const nextMonth = months[index + 1];
    if (!nextMonth || quarterLabel(nextMonth.period_key) !== quarterKey) {
      rows.push(quarterRow);
    }

    const yearKey = month.period_key.slice(0, 4);
    const yearRow = years.get(yearKey) ?? {
      period_key: yearKey,
      period_label: `Soucet ${yearKey}`,
      date_from: month.date_from,
      date_to: month.date_to,
      hours: "0.00",
      level: "year" as const
    };
    yearRow.date_to = month.date_to;
    yearRow.hours = addHours(yearRow.hours, month.hours);
    years.set(yearKey, yearRow);

    const nextYear = nextMonth?.period_key.slice(0, 4);
    if (!nextMonth || nextYear !== yearKey) {
      rows.push(yearRow);
    }

    total ??= {
      period_key: "total",
      period_label: "Celkem",
      date_from: month.date_from,
      date_to: month.date_to,
      hours: "0.00",
      level: "total"
    };
    total.date_to = month.date_to;
    total.hours = addHours(total.hours, month.hours);
  }

  if (total) {
    rows.push(total);
  }
  return rows;
}

export default function Home() {
  const [section, setSection] = useState<Section>("activities");
  const [draft, setDraft] = useState<EntryDraft>(emptyDraft);
  const [activities, setActivities] = useState<ActivityRow[]>([]);
  const [statsPeriodSummaries, setStatsPeriodSummaries] = useState<Record<SummaryGroup, PeriodRow[]>>({
    day: [],
    week: [],
    month: [],
    year: []
  });
  const [statsMonths, setStatsMonths] = useState<PeriodRow[]>([]);
  const [categoryPeriods, setCategoryPeriods] = useState<CategoryPeriodRow[]>([]);
  const [statsProjects, setStatsProjects] = useState<ProjectRow[]>([]);
  const [selectedStatsPeriod, setSelectedStatsPeriod] = useState<StatsPeriodRow | null>(null);
  const [selectedPeriodProjects, setSelectedPeriodProjects] = useState<ProjectRow[]>([]);
  const [categoryComparison, setCategoryComparison] = useState<CategoryComparison | null>(null);
  const [overheadTickets, setOverheadTickets] = useState<OverheadTicket[]>([]);
  const [filters, setFilters] = useState<Filters>(defaultFilters);
  const [statsDateFrom, setStatsDateFrom] = useState("2024-01-01");
  const [statsDateTo, setStatsDateTo] = useState(today());
  const [overheadProject, setOverheadProject] = useState("");
  const [overheadActiveOn, setOverheadActiveOn] = useState("");
  const [overheadCurrentOnly, setOverheadCurrentOnly] = useState(true);
  const [bulkValidFrom, setBulkValidFrom] = useState("");
  const [bulkValidTo, setBulkValidTo] = useState("");
  const [textEntry, setTextEntry] = useState("");
  const [voiceText, setVoiceText] = useState("");
  const [editingEntryId, setEditingEntryId] = useState<string | null>(null);
  const [selectedActivityIds, setSelectedActivityIds] = useState<string[]>([]);
  const [bulkCopyDate, setBulkCopyDate] = useState(today());
  const [message, setMessage] = useState("");
  const [token, setToken] = useState("");
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [userDraft, setUserDraft] = useState<UserDraft>(emptyUserDraft);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loginMessage, setLoginMessage] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const totalVisibleHours = useMemo(
    () => activities.reduce((sum, row) => sum + Number(row.duration_hours || 0), 0).toFixed(2),
    [activities]
  );
  const totalEffectiveHours = useMemo(
    () => activities.reduce((sum, row) => sum + Number(row.effective_hours || 0), 0).toFixed(2),
    [activities]
  );

  const groupedActivities = useMemo(() => {
    const groups: { date: string; rows: ActivityRow[]; hours: string; effectiveHours: string }[] = [];
    for (const row of activities) {
      const last = groups[groups.length - 1];
      if (last?.date === row.spent_on) {
        last.rows.push(row);
        last.hours = (Number(last.hours) + Number(row.duration_hours || 0)).toFixed(2);
        last.effectiveHours = (Number(last.effectiveHours) + Number(row.effective_hours || 0)).toFixed(2);
      } else {
        groups.push({
          date: row.spent_on,
          rows: [row],
          hours: Number(row.duration_hours || 0).toFixed(2),
          effectiveHours: Number(row.effective_hours || 0).toFixed(2)
        });
      }
    }
    return groups;
  }, [activities]);

  const statsRows = useMemo(() => buildStatsRows(statsMonths), [statsMonths]);
  const chartMax = useMemo(() => {
    const values = categoryPeriods.flatMap((row) => categorySeries.map((series) => Number(row[series.key] || 0)));
    return Math.max(1, ...values);
  }, [categoryPeriods]);
  const selectedActivities = useMemo(
    () => activities.filter((row) => selectedActivityIds.includes(row.id)),
    [activities, selectedActivityIds]
  );

  function authHeaders(extra?: HeadersInit): HeadersInit {
    return {
      ...(extra ?? {}),
      Authorization: `Bearer ${token}`
    };
  }

  function entryPayload(value: EntryDraft) {
    return {
      ...value,
      started_at: value.started_at || null,
      ended_at: value.ended_at || null,
      category_code: value.category_code || null,
      ticket_external_id: value.ticket_external_id || null,
      project_name: value.project_name || null,
      transport_name: value.transport_name || null,
      km: value.km || null,
      reported_status: value.reported_status || null
    };
  }

  async function apiFetch(path: string, init?: RequestInit) {
    const response = await fetch(`${apiUrl}${path}`, {
      ...init,
      headers: authHeaders(init?.headers)
    });
    if (response.status === 401) {
      logout();
      throw new Error("Přihlášení vypršelo, přihlaste se znovu.");
    }
    return response;
  }

  async function loadActivities(nextFilters = filters) {
    const query = buildQuery({ ...nextFilters, limit: "200" });
    const response = await apiFetch(`/time-entries?${query}`);
    setActivities(await response.json());
    setSelectedActivityIds([]);
  }

  async function loadStats(dateFrom = statsDateFrom, dateTo = statsDateTo) {
    const query = buildQuery({ date_from: dateFrom, date_to: dateTo });
    const [monthRes, categoryRes, projectRes] = await Promise.all([
      apiFetch(`/statistics/periods?${buildQuery({ group_by: "month", date_from: dateFrom, date_to: dateTo })}`),
      apiFetch(`/statistics/category-periods?${query}`),
      apiFetch(`/statistics/projects?${query}`)
    ]);
    setStatsMonths(await monthRes.json());
    setCategoryPeriods(await categoryRes.json());
    setStatsProjects(await projectRes.json());
    setStatsPeriodSummaries({ day: [], week: [], month: [], year: [] });
    setSelectedStatsPeriod(null);
    setSelectedPeriodProjects([]);
  }

  async function loadCategoryComparison() {
    const response = await apiFetch("/statistics/category-comparison");
    setCategoryComparison(await response.json());
  }

  async function loadPeriodProjects(period: StatsPeriodRow) {
    setSelectedStatsPeriod(period);
    const query = buildQuery({ date_from: period.date_from, date_to: period.date_to });
    const response = await apiFetch(`/statistics/projects?${query}`);
    setSelectedPeriodProjects(await response.json());
  }

  async function loadOverheadTickets(project = overheadProject, activeOn = overheadCurrentOnly ? today() : overheadActiveOn) {
    const query = buildQuery({ project, active_on: activeOn, limit: "300" });
    const response = await apiFetch(`/overhead-tickets?${query}`);
    setOverheadTickets(await response.json());
  }

  async function loadCurrentUser() {
    const response = await apiFetch("/auth/me");
    const user = await response.json();
    setCurrentUser(user);
    return user as CurrentUser;
  }

  async function loadUsers() {
    const response = await apiFetch("/users");
    setUsers(await response.json());
  }

  async function refreshAll() {
    const user = currentUser ?? await loadCurrentUser();
    const requests = [loadActivities(), loadStats(), loadOverheadTickets(), loadCategoryComparison()];
    if (user.role === "admin") {
      requests.push(loadUsers());
    }
    await Promise.all(requests);
  }

  useEffect(() => {
    const storedToken = window.localStorage.getItem("activities_token");
    if (storedToken) {
      setToken(storedToken);
    }
  }, []);

  useEffect(() => {
    if (!token) {
      return;
    }
    refreshAll().catch((error) => setMessage(error.message || "API zatim neodpovida."));
  }, [token]);

  async function login(event: FormEvent) {
    event.preventDefault();
    setLoginMessage("");
    const response = await fetch(`${apiUrl}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password })
    });
    if (!response.ok) {
      setLoginMessage("Prihlaseni se nepodarilo.");
      return;
    }
    const data = await response.json();
    window.localStorage.setItem("activities_token", data.access_token);
    setToken(data.access_token);
    setPassword("");
  }

  function logout() {
    window.localStorage.removeItem("activities_token");
    setToken("");
    setCurrentUser(null);
    setActivities([]);
    setStatsMonths([]);
    setStatsProjects([]);
    setOverheadTickets([]);
    setCategoryComparison(null);
    setUsers([]);
  }

  async function saveEntry(event?: FormEvent) {
    event?.preventDefault();
    const response = await apiFetch(editingEntryId ? `/time-entries/${editingEntryId}` : "/time-entries", {
      method: editingEntryId ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(entryPayload(draft))
    });
    if (!response.ok) {
      setMessage("Zaznam se nepodarilo ulozit.");
      return;
    }
    setMessage(editingEntryId ? "Zaznam upraven." : "Zaznam ulozen.");
    setEditingEntryId(null);
    setDraft({ ...emptyDraft, spent_on: draft.spent_on });
    setTextEntry("");
    await Promise.all([loadActivities(), loadStats(), loadCategoryComparison()]);
  }

  async function parseTextEntry() {
    const response = await apiFetch("/time-entries/parse-text", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: textEntry,
        spent_on: draft.spent_on,
        category_code: draft.category_code || null
      })
    });
    const parsed = await response.json();
    setDraft((current) => ({
      ...current,
      ...parsed.draft,
      category_code: parsed.draft.category_code ?? current.category_code ?? "",
      reported_status: current.reported_status
    }));
    setMessage(parsed.matched_ticket ? `Vybran tiket ${parsed.matched_ticket.external_id}.` : parsed.confidence_notes.join(" "));
  }

  async function parseVoice() {
    const response = await apiFetch("/voice/parse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: voiceText })
    });
    const parsed = await response.json();
    const projectName = parsed.draft.project_name ?? draft.project_name;
    setDraft((current) => ({
      ...current,
      ...parsed.draft,
      duration_hours: current.duration_hours,
      category_code: current.category_code || inferredCategory(projectName)
    }));
    setMessage(parsed.confidence_notes.join(" "));
  }

  async function applyFilters(event: FormEvent) {
    event.preventDefault();
    await loadActivities(filters);
  }

  async function exportActivities() {
    const query = buildQuery(filters);
    const response = await apiFetch(`/time-entries/export.xlsx?${query}`);
    if (!response.ok) {
      setMessage("Export se nepodarilo vytvorit.");
      return;
    }
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `aktivity-${today()}.xlsx`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  }

  async function deleteRow(row: ActivityRow) {
    const confirmed = window.confirm(`Opravdu smazat aktivitu ${row.spent_on} ${timeValue(row.started_at)} - ${row.description}?`);
    if (!confirmed) {
      return;
    }
    const response = await apiFetch(`/time-entries/${row.id}`, { method: "DELETE" });
    if (!response.ok) {
      setMessage("Zaznam se nepodarilo smazat.");
      return;
    }
    if (editingEntryId === row.id) {
      setEditingEntryId(null);
      setDraft({ ...emptyDraft, spent_on: draft.spent_on });
    }
    setMessage("Zaznam smazan.");
    await Promise.all([loadActivities(), loadStats(), loadCategoryComparison()]);
  }

  async function applyStatsPeriod(event: FormEvent) {
    event.preventDefault();
    await loadStats(statsDateFrom, statsDateTo);
  }

  async function applyOverheadFilters(event?: FormEvent) {
    event?.preventDefault();
    await loadOverheadTickets(overheadProject, overheadCurrentOnly ? today() : overheadActiveOn);
  }

  function toggleActivitySelection(id: string) {
    setSelectedActivityIds((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id]
    );
  }

  function toggleAllVisibleActivities(checked: boolean) {
    setSelectedActivityIds(checked ? activities.map((row) => row.id) : []);
  }

  async function bulkCopyActivities(event: FormEvent) {
    event.preventDefault();
    if (!selectedActivities.length) {
      setMessage("Nejsou vybrane zadne aktivity ke kopirovani.");
      return;
    }
    for (const row of selectedActivities) {
      const response = await apiFetch("/time-entries", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          spent_on: bulkCopyDate,
          started_at: timeValue(row.started_at) || null,
          ended_at: timeValue(row.ended_at) || null,
          duration_hours: row.duration_hours,
          category_code: row.category_code,
          description: row.description,
          ticket_external_id: row.ticket_external_id,
          project_name: row.project_name,
          transport_name: row.transport_name,
          km: row.km,
          reported_status: row.reported_status
        })
      });
      if (!response.ok) {
        setMessage("Hromadne kopirovani se nepodarilo dokoncit.");
        return;
      }
    }
    setMessage(`Zkopirovano ${selectedActivities.length} aktivit na ${bulkCopyDate}.`);
    setSelectedActivityIds([]);
    await Promise.all([loadActivities(), loadStats(), loadCategoryComparison()]);
  }

  async function bulkUpdateOverheadValidity(event: FormEvent) {
    event.preventDefault();
    const externalIds = overheadTickets.map((ticket) => ticket.external_id);
    if (!externalIds.length) {
      setMessage("Neni vybran zadny rezijni tiket.");
      return;
    }
    const response = await apiFetch("/overhead-tickets/validity", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        external_ids: externalIds,
        valid_from: bulkValidFrom || null,
        valid_to: bulkValidTo || null
      })
    });
    if (!response.ok) {
      setMessage("Platnost tiketu se nepodarilo hromadne upravit.");
      return;
    }
    const result = await response.json();
    setMessage(`Upravena platnost u ${result.updated_count} rezijnich tiketu.`);
    await applyOverheadFilters();
  }

  async function saveUser(event: FormEvent) {
    event.preventDefault();
    const response = await apiFetch("/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(userDraft)
    });
    if (!response.ok) {
      setMessage("Uzivatele se nepodarilo ulozit.");
      return;
    }
    setMessage("Uzivatel ulozen.");
    setUserDraft(emptyUserDraft);
    await loadUsers();
  }

  async function updateUser(usernameValue: string, payload: Partial<UserDraft>) {
    const response = await apiFetch(`/users/${encodeURIComponent(usernameValue)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!response.ok) {
      setMessage("Uzivatele se nepodarilo upravit.");
      return;
    }
    setMessage("Uzivatel upraven.");
    await loadUsers();
  }

  function switchSection(nextSection: Section) {
    setSection(nextSection);
    setMenuOpen(false);
  }

  function updateProject(projectName: string) {
    setDraft((current) => ({
      ...current,
      project_name: projectName,
      category_code: current.category_code || inferredCategory(projectName)
    }));
  }

  function copyRow(row: ActivityRow) {
    setEditingEntryId(null);
    setDraft({
      spent_on: row.spent_on,
      started_at: timeValue(row.started_at),
      ended_at: timeValue(row.ended_at),
      duration_hours: row.duration_hours,
      category_code: row.category_code ?? "",
      description: row.description,
      ticket_external_id: row.ticket_external_id ?? "",
      project_name: row.project_name ?? "",
      transport_name: row.transport_name ?? "",
      km: row.km ?? "",
      reported_status: row.reported_status ?? ""
    });
    switchSection("activities");
  }

  function editRow(row: ActivityRow) {
    setEditingEntryId(row.id);
    setDraft({
      spent_on: row.spent_on,
      started_at: timeValue(row.started_at),
      ended_at: timeValue(row.ended_at),
      duration_hours: row.duration_hours,
      category_code: row.category_code ?? "",
      description: row.description,
      ticket_external_id: row.ticket_external_id ?? "",
      project_name: row.project_name ?? "",
      transport_name: row.transport_name ?? "",
      km: row.km ?? "",
      reported_status: row.reported_status ?? ""
    });
    switchSection("activities");
  }

  function cancelEdit() {
    setEditingEntryId(null);
    setDraft({ ...emptyDraft, spent_on: draft.spent_on });
  }

  const visibleSections = sections.filter((item) => !item.adminOnly || currentUser?.role === "admin");

  if (!token) {
    return (
      <main className="loginShell">
        <form className="loginPanel" onSubmit={login}>
          <div className="loginBrand">
            <span className="loginBrandIcon">A</span>
            <div>
              <h1>Activities</h1>
              <p className="muted">Evidence odpracovane doby, aktivit a rezijnich tiketu.</p>
            </div>
          </div>
          <p className="loginIntro">Prihlaste se svym uctem pro zapis casu, kontrolu statistik a praci s vykazovanymi aktivitami.</p>
          <label>Uzivatel<input autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} /></label>
          <label>Heslo<input autoComplete="current-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
          {loginMessage && <p className="message">{loginMessage}</p>}
          <button type="submit">Prihlasit</button>
        </form>
      </main>
    );
  }

  return (
    <main className={`appShell ${sidebarCollapsed ? "sidebarCollapsed" : ""}`}>
      {menuOpen && <button className="menuBackdrop" aria-label="Zavrit menu" onClick={() => setMenuOpen(false)} />}

      <aside className={`sidebar ${menuOpen ? "open" : ""} ${sidebarCollapsed ? "collapsed" : ""}`}>
        <div className="brand">
          <span className="brandMark">A</span>
          <div className="brandText">
            <h1>Activities</h1>
            <p>Evidence casu</p>
          </div>
        </div>
        <button className="iconButton secondary collapseButton" onClick={() => setSidebarCollapsed((value) => !value)} title={sidebarCollapsed ? "Rozbalit menu" : "Sbalit menu"}>
          {sidebarCollapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
        </button>
        <nav className="sideNav" aria-label="Sekce aplikace">
          {visibleSections.map((item) => {
            const Icon = item.icon;
            return (
              <button key={item.id} className={section === item.id ? "active" : ""} onClick={() => switchSection(item.id)} title={item.label}>
                <Icon size={18} /> <span className="navLabel">{item.label}</span>
              </button>
            );
          })}
        </nav>
        <button className="secondary logoutButton" onClick={logout} title="Odhlasit">
          <LogOut size={18} /> <span className="logoutLabel">Odhlasit</span>
        </button>
      </aside>

      <section className="contentShell">
        <header className="topbar">
          <div className="titleRow">
            <button className="iconButton mobileMenuButton" onClick={() => setMenuOpen(true)} title="Otevrit menu">
              <Menu size={18} />
            </button>
            <div>
              <h1>{sections.find((item) => item.id === section)?.label}</h1>
              <p>{currentUser?.username} - {currentUser?.role}</p>
            </div>
          </div>
          <button className="iconButton" onClick={refreshAll} title="Obnovit data">
            <RefreshCw size={18} />
          </button>
        </header>

        {message && <p className="message banner">{message}</p>}

        {categoryComparison && (
          <section className="topSummary">
            <div className="summaryHeader">
              <h2>Aktualni vykon</h2>
              <p className="muted">
                Tyden {categoryComparison.current_week_from} - {categoryComparison.current_week_to}; mesic {categoryComparison.current_month_from} - {categoryComparison.current_month_to}
              </p>
            </div>
            <div className="categoryCards">
              {categoryComparison.rows.map((row) => (
                <div className="categoryCard" key={row.category_key}>
                  <h3>{row.label}</h3>
                  <div className="metricLine">
                    <span>Tyden</span>
                    <strong>{row.current_week_hours}</strong>
                    <small className={Number(row.week_delta_hours) >= 0 ? "positive" : "negative"}>
                      {Number(row.week_delta_hours) >= 0 ? "+" : ""}{row.week_delta_hours}
                    </small>
                  </div>
                  <div className="metricLine">
                    <span>Mesic</span>
                    <strong>{row.current_month_hours}</strong>
                    <small className={Number(row.month_delta_hours) >= 0 ? "positive" : "negative"}>
                      {Number(row.month_delta_hours) >= 0 ? "+" : ""}{row.month_delta_hours}
                    </small>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {section === "activities" && (
          <>
            <section className="workspace">
              <form className="panel entryPanel" onSubmit={saveEntry}>
                <div className="panelHeader">
                  <h2>{editingEntryId ? "Uprava zaznamu" : "Novy zaznam"}</h2>
                  <Save size={18} />
                </div>

                <div className="quickEntry">
                  <label>Datum<input type="date" value={draft.spent_on} onChange={(e) => setDraft({ ...draft, spent_on: e.target.value })} /></label>
                  <label>
                    Text
                    <input
                      value={textEntry}
                      onChange={(event) => setTextEntry(event.target.value)}
                      placeholder="08:00-08:30: E-maily Z: ZAKO SMLS"
                    />
                  </label>
                  <button type="button" onClick={parseTextEntry}>
                    <Search size={18} /> Rozpoznat
                  </button>
                </div>

                <div className="gridForm">
                  <label>Od<input type="time" value={draft.started_at} onChange={(e) => setDraft({ ...draft, started_at: e.target.value })} /></label>
                  <label>Do<input type="time" value={draft.ended_at} onChange={(e) => setDraft({ ...draft, ended_at: e.target.value })} /></label>
                  <label>Hodin<input type="number" step="0.25" value={draft.duration_hours} onChange={(e) => setDraft({ ...draft, duration_hours: e.target.value })} /></label>
                  <label>Kat.<input value={draft.category_code} onChange={(e) => setDraft({ ...draft, category_code: e.target.value })} /></label>
                  <label>Tiket<input value={draft.ticket_external_id} onChange={(e) => setDraft({ ...draft, ticket_external_id: e.target.value })} /></label>
                  <label>Zakazka<input value={draft.project_name} onChange={(e) => updateProject(e.target.value)} /></label>
                  <label>Doprava<input list="transport-options" value={draft.transport_name} onChange={(e) => setDraft({ ...draft, transport_name: e.target.value })} /></label>
                  <label>km<input type="number" step="0.1" value={draft.km} onChange={(e) => setDraft({ ...draft, km: e.target.value })} /></label>
                  <label>Zapsano<input value={draft.reported_status} onChange={(e) => setDraft({ ...draft, reported_status: e.target.value })} /></label>
                </div>
                <datalist id="transport-options">
                  {transportOptions.map((transport) => <option key={transport} value={transport} />)}
                </datalist>
                <label>Popis<textarea value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /></label>
              <div className="actions">
                  <button type="submit"><Save size={18} /> {editingEntryId ? "Ulozit zmeny" : "Ulozit"}</button>
                  {editingEntryId && <button type="button" className="secondary" onClick={cancelEdit}><X size={18} /> Zrusit upravu</button>}
                </div>
              </form>

              <section className="panel voicePanel">
                <div className="panelHeader">
                  <h2>Hlasovy vstup</h2>
                  <Mic size={18} />
                </div>
                <textarea value={voiceText} onChange={(e) => setVoiceText(e.target.value)} placeholder="Dnes od 7 do 7:30 e-maily pro ZAKO ticket 39365" />
                <button onClick={parseVoice}><Mic size={18} /> Prevest do navrhu</button>
              </section>
            </section>

            <section className="panel widePanel">
              <div className="panelHeader">
                <div>
                  <h2>Seznam aktivit</h2>
                  <p className="muted">Zobrazeno {activities.length} zaznamu, zadano {totalVisibleHours} h, skutecne {totalEffectiveHours} h</p>
                </div>
                <ListFilter size={18} />
              </div>
              <form className="filterBar" onSubmit={applyFilters}>
                <label>Od<input type="date" value={filters.date_from} onChange={(e) => setFilters({ ...filters, date_from: e.target.value })} /></label>
                <label>Do<input type="date" value={filters.date_to} onChange={(e) => setFilters({ ...filters, date_to: e.target.value })} /></label>
                <label>Zakazka<input value={filters.project} onChange={(e) => setFilters({ ...filters, project: e.target.value })} /></label>
                <label>Tiket<input value={filters.ticket} onChange={(e) => setFilters({ ...filters, ticket: e.target.value })} /></label>
                <label>Text<input value={filters.text} onChange={(e) => setFilters({ ...filters, text: e.target.value })} /></label>
                <button type="submit"><Search size={18} /> Filtrovat</button>
                <button type="button" className="secondary" onClick={exportActivities}><Download size={18} /> Excel</button>
              </form>
              <form className="bulkCopyForm" onSubmit={bulkCopyActivities}>
                <label>Kopirovat na<input type="date" value={bulkCopyDate} onChange={(event) => setBulkCopyDate(event.target.value)} /></label>
                <span className="bulkInfo">Vybrano {selectedActivityIds.length}</span>
                <button type="submit"><CheckSquare size={18} /> Zkopirovat vybrane</button>
              </form>

              <div className="tableWrap">
                <table>
                  <thead>
                    <tr>
                      <th><input type="checkbox" checked={activities.length > 0 && selectedActivityIds.length === activities.length} onChange={(event) => toggleAllVisibleActivities(event.target.checked)} /></th>
                      <th>Datum</th><th>Den</th><th>Od</th><th>Do</th><th>Zadano</th><th>Prekryv</th><th>Skutecne</th><th>Kat.</th><th>Tiket</th><th>Zakazka</th><th>Doprava</th><th>km</th><th>Popis</th><th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {groupedActivities.map((group) => (
                      <Fragment key={group.date}>
                        {group.rows.map((row) => (
                          <tr key={row.id}>
                            <td><input type="checkbox" checked={selectedActivityIds.includes(row.id)} onChange={() => toggleActivitySelection(row.id)} /></td>
                            <td>{row.spent_on}</td>
                            <td>{weekdayName(row.spent_on)}</td>
                            <td>{timeValue(row.started_at)}</td>
                            <td>{timeValue(row.ended_at)}</td>
                            <td>{row.duration_hours}</td>
                            <td>{row.overlap_hours}</td>
                            <td>{row.effective_hours}</td>
                            <td>{row.category_code}</td>
                            <td>{row.ticket_external_id}</td>
                            <td>{row.project_name}</td>
                            <td>{row.transport_name}</td>
                            <td>{formatKm(row.km)}</td>
                            <td className="descriptionCell">{row.description}</td>
                            <td className="rowActions">
                              <button className="iconButton secondary" onClick={() => editRow(row)} title="Upravit radek"><Edit3 size={16} /></button>
                              <button className="iconButton secondary" onClick={() => copyRow(row)} title="Kopirovat radek"><Copy size={16} /></button>
                              <button className="iconButton danger" onClick={() => deleteRow(row)} title="Smazat radek"><Trash2 size={16} /></button>
                            </td>
                          </tr>
                        ))}
                        <tr className="subtotalRow">
                          <td colSpan={5}>Soucet dne {group.date} ({weekdayName(group.date)})</td>
                          <td>{group.hours}</td>
                          <td></td>
                          <td>{group.effectiveHours}</td>
                          <td colSpan={7}></td>
                        </tr>
                      </Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}

        {section === "statistics" && (
          <section className="panel widePanel">
            <div className="panelHeader">
              <div>
                <h2>Statistiky</h2>
              <p className="muted">Nejprve zvolte obdobi, potom kliknete na mesic, kvartal, rok nebo celkovy soucet.</p>
              </div>
              <BarChart3 size={18} />
            </div>
            <form className="statsFilters" onSubmit={applyStatsPeriod}>
              <label>Obdobi od<input type="date" value={statsDateFrom} onChange={(e) => setStatsDateFrom(e.target.value)} /></label>
              <label>Obdobi do<input type="date" value={statsDateTo} onChange={(e) => setStatsDateTo(e.target.value)} /></label>
              <button type="submit"><Search size={18} /> Nacist statistiku</button>
            </form>
            <div className="chartPanel">
              <div className="chartHeader">
                <h3>Casovy prubeh podle kategorii</h3>
                <p className="muted">Mesicni skutecne hodiny, jednotne meritko {chartMax.toFixed(0)} h.</p>
              </div>
              <div className="smallCharts">
                {categorySeries.map((series) => (
                  <div className="smallChart" key={series.key}>
                    <div className="smallChartTitle">
                      <span><i style={{ background: series.color }} /> {series.label}</span>
                      <strong>
                        {categoryPeriods.reduce((sum, row) => sum + Number(row[series.key] || 0), 0).toFixed(2)} h
                      </strong>
                    </div>
                    <div className="barChart" role="img" aria-label={`Mesicni prubeh ${series.label}`}>
                      {categoryPeriods.map((row) => {
                        const value = Number(row[series.key] || 0);
                        const height = Math.max(2, (value / chartMax) * 100);
                        return (
                          <div className="barColumn" key={row.period_key} title={`${row.period_label}: ${value.toFixed(2)} h`}>
                            <span className="barValue">{value ? value.toFixed(0) : ""}</span>
                            <div className="barTrack">
                              <div className="barFill" style={{ height: `${height}%`, background: series.color }} />
                            </div>
                            <span className="barLabel">{row.period_label.slice(5) || row.period_label}</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div className="statsDrilldown">
              <div>
                <h3>Mesicni soucty vcetne mezisouctu</h3>
                <div className="tableWrap statsTable">
                  <table>
                    <thead><tr><th>Obdobi</th><th>Od</th><th>Do</th><th>Hodin</th></tr></thead>
                    <tbody>
                      {statsRows.map((row) => (
                        <tr className={`${selectedStatsPeriod?.period_key === row.period_key ? "selectedRow" : ""} ${row.level !== "month" ? "subtotalRow clickableRow" : "clickableRow"}`} key={`${row.level}-${row.period_key}`} onClick={() => loadPeriodProjects(row)}>
                          <td>{row.period_label}</td><td>{row.date_from}</td><td>{row.date_to}</td><td>{row.hours}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              <div>
                <h3>{selectedStatsPeriod ? `Zakazky v obdobi ${selectedStatsPeriod.period_label}` : "Zakazky ve zvolenem obdobi"}</h3>
                <div className="tableWrap statsTable">
                  <table>
                    <thead><tr><th>Zakazka</th><th>Hodin</th></tr></thead>
                    <tbody>
                      {(selectedStatsPeriod ? selectedPeriodProjects : statsProjects).slice(0, 80).map((row) => (
                        <tr key={row.project_name}><td>{row.project_name}</td><td>{row.hours}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </section>
        )}

        {section === "overhead" && (
          <section className="panel widePanel">
            <div className="panelHeader">
              <div>
                <h2>Rezijni tikety</h2>
                <p className="muted">Tikety s platnosti podle obdobi z Excelu</p>
              </div>
              <Ticket size={18} />
            </div>
            <form className="filterBar overheadFilters" onSubmit={applyOverheadFilters}>
              <label>Zakazka<input value={overheadProject} onChange={(e) => setOverheadProject(e.target.value)} /></label>
              <label>Platne k<input type="date" disabled={overheadCurrentOnly} value={overheadCurrentOnly ? today() : overheadActiveOn} onChange={(e) => setOverheadActiveOn(e.target.value)} /></label>
              <label className="checkLabel"><input type="checkbox" checked={overheadCurrentOnly} onChange={(e) => setOverheadCurrentOnly(e.target.checked)} /> Jen aktualni</label>
              <button type="submit"><Search size={18} /> Filtrovat</button>
            </form>
            {currentUser?.role === "admin" && (
              <form className="bulkValidityForm" onSubmit={bulkUpdateOverheadValidity}>
                <label>Nova platnost od<input type="date" value={bulkValidFrom} onChange={(event) => setBulkValidFrom(event.target.value)} /></label>
                <label>Nova platnost do<input type="date" value={bulkValidTo} onChange={(event) => setBulkValidTo(event.target.value)} /></label>
                <button type="submit"><Save size={18} /> Upravit zobrazenych {overheadTickets.length}</button>
              </form>
            )}
            <div className="tableWrap">
              <table>
                <thead><tr><th>Tiket</th><th>Zakazka</th><th>Predmet</th><th>Obdobi</th><th>Platnost od</th><th>Platnost do</th></tr></thead>
                <tbody>
                  {overheadTickets.map((ticket) => (
                    <tr key={ticket.external_id}>
                      <td>{ticket.external_id}</td>
                      <td>{ticket.project_name}</td>
                      <td>{ticket.subject}</td>
                      <td>{ticket.source_period}</td>
                      <td>{formatDateTime(ticket.valid_from)}</td>
                      <td>{formatDateTime(ticket.valid_to)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {section === "users" && currentUser?.role === "admin" && (
          <section className="panel widePanel">
            <div className="panelHeader">
              <div>
                <h2>Sprava uzivatelu</h2>
                <p className="muted">Role admin spravuje uzivatele, editor zapisuje aktivity, viewer jen cte.</p>
              </div>
              <Users size={18} />
            </div>
            <form className="userForm" onSubmit={saveUser}>
              <label>Uzivatel<input value={userDraft.username} onChange={(event) => setUserDraft({ ...userDraft, username: event.target.value })} /></label>
              <label>Heslo<input type="password" value={userDraft.password} onChange={(event) => setUserDraft({ ...userDraft, password: event.target.value })} /></label>
              <label>
                Role
                <select value={userDraft.role} onChange={(event) => setUserDraft({ ...userDraft, role: event.target.value })}>
                  <option value="viewer">viewer</option>
                  <option value="editor">editor</option>
                  <option value="admin">admin</option>
                </select>
              </label>
              <label className="checkLabel"><input type="checkbox" checked={userDraft.is_active} onChange={(event) => setUserDraft({ ...userDraft, is_active: event.target.checked })} /> Aktivni</label>
              <button type="submit"><Save size={18} /> Pridat</button>
            </form>
            <div className="tableWrap">
              <table>
                <thead><tr><th>Uzivatel</th><th>Role</th><th>Stav</th><th>Nove heslo</th><th>Akce</th></tr></thead>
                <tbody>
                  {users.map((user) => (
                    <tr key={user.username}>
                      <td>{user.username}</td>
                      <td>
                        <select value={user.role} onChange={(event) => updateUser(user.username, { role: event.target.value })}>
                          <option value="viewer">viewer</option>
                          <option value="editor">editor</option>
                          <option value="admin">admin</option>
                        </select>
                      </td>
                      <td>
                        <label className="checkLabel tableCheck">
                          <input type="checkbox" checked={user.is_active} onChange={(event) => updateUser(user.username, { is_active: event.target.checked })} />
                          {user.is_active ? "Aktivni" : "Neaktivni"}
                        </label>
                      </td>
                      <td>
                        <input
                          type="password"
                          placeholder="Vyplnit jen pri zmene"
                          onBlur={(event) => {
                            if (event.target.value) {
                              updateUser(user.username, { password: event.target.value });
                              event.target.value = "";
                            }
                          }}
                        />
                      </td>
                      <td>{user.username === currentUser.username ? "Prave prihlasen" : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </section>
    </main>
  );
}
