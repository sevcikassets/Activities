"use client";

import { BarChart3, CheckSquare, Copy, Download, Edit3, Fuel, ListFilter, LogOut, Menu, Mic, PanelLeftClose, PanelLeftOpen, RefreshCw, Save, Search, Table2, Ticket, Trash2, Users, X } from "lucide-react";
import { Fragment, FormEvent, KeyboardEvent, useEffect, useMemo, useState } from "react";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Section = "activities" | "statistics" | "fuel" | "overhead" | "users";
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
  movement_hours: string;
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

type FuelVehicle = {
  id: string;
  code: string;
  name: string;
  is_active: boolean;
  sort_order: number;
};

type FuelEntry = {
  id: string;
  vehicle_id: string;
  vehicle_name: string;
  purchased_on: string;
  purchased_at: string | null;
  station: string | null;
  fuel_type: string | null;
  odometer_km: string | null;
  liters: string | null;
  total_price_vat: string | null;
  total_price_no_vat: string | null;
  price_per_liter: string | null;
  trip_km: string | null;
  full_tank: boolean | null;
  average_consumption: string | null;
  note: string | null;
  receipt_photo_path: string | null;
  dashboard_photo_path: string | null;
  source: string;
  source_sheet: string | null;
  source_row: number | null;
};

type FuelDraft = {
  vehicle_id: string;
  purchased_on: string;
  purchased_at: string;
  station: string;
  fuel_type: string;
  odometer_km: string;
  liters: string;
  total_price_vat: string;
  total_price_no_vat: string;
  price_per_liter: string;
  trip_km: string;
  full_tank: string;
  average_consumption: string;
  note: string;
};

type FuelDisplayRow =
  | { kind: "entry"; entry: FuelEntry }
  | { kind: "subtotal"; key: string; label: string; level: "month" | "year"; liters: string; total: string; tripKm: string; average: string };

type FuelConsumptionPoint = {
  key: string;
  label: string;
  value: number;
  liters: number;
  tripKm: number;
  entries: number;
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

function dateInputValue(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

const today = () => dateInputValue(new Date());

function defaultStatsDateFrom() {
  const current = new Date();
  const year = current.getFullYear();
  const isAfterFirstQuarter = current.getMonth() >= 3;
  return `${isAfterFirstQuarter ? year : year - 1}-01-01`;
}

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

const emptyFuelDraft: FuelDraft = {
  vehicle_id: "",
  purchased_on: today(),
  purchased_at: "",
  station: "",
  fuel_type: "Natural 95",
  odometer_km: "",
  liters: "",
  total_price_vat: "",
  total_price_no_vat: "",
  price_per_liter: "",
  trip_km: "",
  full_tank: "true",
  average_consumption: "",
  note: ""
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
  { key: "movement_hours", label: "Pohyb", color: "#2f855a" },
  { key: "tanaka_hours", label: "TANAKA", color: "#3f5f8f" }
] as const;

const sections: { id: Section; label: string; icon: typeof Table2; adminOnly?: boolean }[] = [
  { id: "activities", label: "Aktivity", icon: Table2 },
  { id: "statistics", label: "Statistiky", icon: BarChart3 },
  { id: "fuel", label: "PHM", icon: Fuel },
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

function timeMinutes(value: string | null) {
  const time = timeValue(value);
  if (!time) {
    return -1;
  }
  const [hours, minutes] = time.split(":").map(Number);
  return hours * 60 + minutes;
}

function durationFromTimes(startedAt: string, endedAt: string) {
  if (!startedAt || !endedAt) {
    return "";
  }
  const start = timeMinutes(startedAt);
  let end = timeMinutes(endedAt);
  if (start < 0 || end < 0) {
    return "";
  }
  if (end < start) {
    end += 24 * 60;
  }
  return ((end - start) / 60).toFixed(2);
}

function overlapHoursForDraft(rows: ActivityRow[], draft: EntryDraft, editingEntryId: string | null) {
  if (!draft.spent_on || !draft.started_at || !draft.ended_at) {
    return "0.00";
  }
  const start = timeMinutes(draft.started_at);
  let end = timeMinutes(draft.ended_at);
  if (start < 0 || end < 0) {
    return "0.00";
  }
  if (end < start) {
    end += 24 * 60;
  }

  const intervals = rows
    .filter((row) => row.id !== editingEntryId && row.spent_on === draft.spent_on && row.started_at && row.ended_at)
    .map((row) => {
      const rowStart = timeMinutes(row.started_at);
      let rowEnd = timeMinutes(row.ended_at);
      if (rowEnd < rowStart) {
        rowEnd += 24 * 60;
      }
      return [Math.max(start, rowStart), Math.min(end, rowEnd)] as const;
    })
    .filter(([overlapStart, overlapEnd]) => overlapEnd > overlapStart)
    .sort(([leftStart], [rightStart]) => leftStart - rightStart);

  const merged: number[][] = [];
  for (const [overlapStart, overlapEnd] of intervals) {
    const previous = merged[merged.length - 1];
    if (!previous || overlapStart > previous[1]) {
      merged.push([overlapStart, overlapEnd]);
    } else {
      previous[1] = Math.max(previous[1], overlapEnd);
    }
  }

  const overlapMinutes = merged.reduce((sum, [overlapStart, overlapEnd]) => sum + overlapEnd - overlapStart, 0);
  return (overlapMinutes / 60).toFixed(2);
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
  return new Intl.NumberFormat("cs-CZ", { maximumFractionDigits: 0 }).format(Math.round(Number(value)));
}

function formatNumber(value: string | number | null | undefined, digits = 2, minimumDigits = digits) {
  if (value === null || value === undefined || value === "") {
    return "";
  }
  return new Intl.NumberFormat("cs-CZ", {
    minimumFractionDigits: minimumDigits,
    maximumFractionDigits: digits
  }).format(Number(value));
}

function formatBool(value: boolean | null) {
  if (value === null) {
    return "";
  }
  return value ? "Ano" : "Ne";
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

function isAutoTimePrefix(value: string) {
  return /^(\d{1,2}:\d{2}-?)?$/.test(value.trim());
}

function stripTextEntryStructure(description: string, projectName: string) {
  let value = description.trim();
  value = value.replace(/^\d{1,2}[:.]\d{2}\s*-\s*\d{1,2}[:.\-]\d{2}\s*:\s*/i, "");
  if (projectName) {
    const escapedProject = projectName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    value = value.replace(new RegExp(`\\s+Z:\\s*${escapedProject}(?:\\s*-\\s*\\d+(?:[,.]\\d+)?)?\\s*$`, "i"), "");
  } else {
    value = value.replace(/\s+Z:\s*.+?(?:\s*-\s*\d+(?:[,.]\d+)?)?\s*$/i, "");
  }
  return value.trim();
}

function quickTextFromDraft(value: EntryDraft) {
  const startedAt = timeValue(value.started_at);
  const endedAt = timeValue(value.ended_at);
  const projectName = (value.project_name || "").trim();
  const description = stripTextEntryStructure(value.raw_text || value.description || "", projectName);
  if (!startedAt || !endedAt || !description || !projectName) {
    return "";
  }
  return `${startedAt}-${endedAt}: ${description} Z: ${projectName}`;
}

function cleanDescriptionFromDraft(value: EntryDraft) {
  return stripTextEntryStructure(value.raw_text || value.description || "", value.project_name || "");
}

function inferredCategory(projectName: string) {
  const normalized = projectName
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
  if (normalized === "abra vr") return "A";
  if (normalized === "anglictina") return "V";
  if (normalized === "rd kvasice" || normalized === "investice" || normalized === "soukrome") return "S";
  if (normalized === "pohyb" || normalized === "cviceni") return "P";
  return "";
}

function addHours(left: string, right: string) {
  return (Number(left || 0) + Number(right || 0)).toFixed(2);
}

function addDays(value: string, days: number) {
  const date = new Date(`${value}T12:00:00`);
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}

function formatOverlap(value: string | null) {
  if (!value || Number(value) === 0) {
    return "";
  }
  return value;
}

function minutesFromTime(value: string | null) {
  const time = timeValue(value);
  if (!time) {
    return null;
  }
  const [hours, minutes] = time.split(":").map(Number);
  return hours * 60 + minutes;
}

function fuelAverage(liters: number, tripKm: number) {
  if (!tripKm) {
    return "";
  }
  return ((liters / tripKm) * 100).toFixed(2);
}

function fuelAverageClass(value: string | null | undefined) {
  if (!value) {
    return "fuelAverageCell empty";
  }
  const numberValue = Number(value);
  if (numberValue >= 10) {
    return "fuelAverageCell high";
  }
  if (numberValue <= 6) {
    return "fuelAverageCell low";
  }
  return "fuelAverageCell";
}

function buildFuelDisplayRows(entries: FuelEntry[]): FuelDisplayRow[] {
  const rows: FuelDisplayRow[] = [];
  const sorted = [...entries].sort((left, right) => {
    const dateCompare = right.purchased_on.localeCompare(left.purchased_on);
    if (dateCompare) return dateCompare;
    return (right.purchased_at || "").localeCompare(left.purchased_at || "");
  });
  let currentMonth = "";
  let currentYear = "";
  let monthLiters = 0;
  let monthTotal = 0;
  let monthTrip = 0;
  let yearLiters = 0;
  let yearTotal = 0;
  let yearTrip = 0;

  function pushMonth() {
    if (!currentMonth) return;
    rows.push({
      kind: "subtotal",
      key: `month-${currentMonth}`,
      label: `Soucet mesice ${currentMonth}`,
      level: "month",
      liters: monthLiters.toFixed(2),
      total: monthTotal.toFixed(2),
      tripKm: monthTrip.toFixed(0),
      average: fuelAverage(monthLiters, monthTrip)
    });
  }

  function pushYear() {
    if (!currentYear) return;
    rows.push({
      kind: "subtotal",
      key: `year-${currentYear}`,
      label: `Soucet roku ${currentYear}`,
      level: "year",
      liters: yearLiters.toFixed(2),
      total: yearTotal.toFixed(2),
      tripKm: yearTrip.toFixed(0),
      average: fuelAverage(yearLiters, yearTrip)
    });
  }

  const firstEntryId = sorted.length ? sorted[sorted.length - 1].id : null;

  for (const entry of sorted) {
    const month = entry.purchased_on.slice(0, 7);
    const year = entry.purchased_on.slice(0, 4);
    if (currentMonth && currentMonth !== month) {
      pushMonth();
      monthLiters = 0;
      monthTotal = 0;
      monthTrip = 0;
    }
    if (currentYear && currentYear !== year) {
      pushYear();
      yearLiters = 0;
      yearTotal = 0;
      yearTrip = 0;
    }
    currentMonth = month;
    currentYear = year;
    if (entry.id !== firstEntryId) {
      monthLiters += Number(entry.liters || 0);
      monthTotal += Number(entry.total_price_vat || 0);
      monthTrip += Number(entry.trip_km || 0);
      yearLiters += Number(entry.liters || 0);
      yearTotal += Number(entry.total_price_vat || 0);
      yearTrip += Number(entry.trip_km || 0);
    }
    rows.push({ kind: "entry", entry });
  }
  pushMonth();
  pushYear();
  return rows;
}

function buildFuelConsumptionPoints(entries: FuelEntry[]): FuelConsumptionPoint[] {
  const months = new Map<string, { liters: number; tripKm: number; entries: number }>();
  const oldestFirst = [...entries].sort((left, right) => {
    const dateCompare = left.purchased_on.localeCompare(right.purchased_on);
    if (dateCompare) return dateCompare;
    return (left.purchased_at || "").localeCompare(right.purchased_at || "");
  });
  const firstEntryId = oldestFirst.length ? oldestFirst[0].id : null;
  for (const entry of entries) {
    if (entry.id === firstEntryId) {
      continue;
    }
    if (!entry.trip_km || !entry.liters) {
      continue;
    }
    const month = entry.purchased_on.slice(0, 7);
    const item = months.get(month) ?? { liters: 0, tripKm: 0, entries: 0 };
    item.liters += Number(entry.liters || 0);
    item.tripKm += Number(entry.trip_km || 0);
    item.entries += 1;
    months.set(month, item);
  }
  return [...months.entries()]
    .filter(([, item]) => item.tripKm > 0)
    .sort(([left], [right]) => left.localeCompare(right))
    .slice(-24)
    .map(([month, item]) => ({
      key: month,
      label: month.slice(2),
      liters: item.liters,
      tripKm: item.tripKm,
      entries: item.entries,
      value: (item.liters / item.tripKm) * 100
    }));
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
  const [fuelVehicles, setFuelVehicles] = useState<FuelVehicle[]>([]);
  const [selectedFuelVehicleId, setSelectedFuelVehicleId] = useState("");
  const [fuelEntries, setFuelEntries] = useState<FuelEntry[]>([]);
  const [fuelDraft, setFuelDraft] = useState<FuelDraft>(emptyFuelDraft);
  const [editingFuelEntryId, setEditingFuelEntryId] = useState<string | null>(null);
  const [receiptPhoto, setReceiptPhoto] = useState<File | null>(null);
  const [dashboardPhoto, setDashboardPhoto] = useState<File | null>(null);
  const [isParsingFuelPhotos, setIsParsingFuelPhotos] = useState(false);
  const [overheadTickets, setOverheadTickets] = useState<OverheadTicket[]>([]);
  const [filters, setFilters] = useState<Filters>(defaultFilters);
  const [statsDateFrom, setStatsDateFrom] = useState(defaultStatsDateFrom);
  const [statsDateTo, setStatsDateTo] = useState(today());
  const [overheadProject, setOverheadProject] = useState("");
  const [overheadActiveOn, setOverheadActiveOn] = useState("");
  const [overheadCurrentOnly, setOverheadCurrentOnly] = useState(true);
  const [bulkValidFrom, setBulkValidFrom] = useState("");
  const [bulkValidTo, setBulkValidTo] = useState("");
  const [textEntry, setTextEntry] = useState("");
  const [textEntryRecognized, setTextEntryRecognized] = useState(false);
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
  const [activityFiltersOpen, setActivityFiltersOpen] = useState(false);
  const [bulkCopyOpen, setBulkCopyOpen] = useState(false);
  const [fuelStatsOpen, setFuelStatsOpen] = useState(false);

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
  const selectedFuelVehicle = useMemo(
    () => fuelVehicles.find((vehicle) => vehicle.id === selectedFuelVehicleId) ?? null,
    [fuelVehicles, selectedFuelVehicleId]
  );
  const fuelDisplayRows = useMemo(() => buildFuelDisplayRows(fuelEntries), [fuelEntries]);
  const fuelConsumptionPoints = useMemo(() => buildFuelConsumptionPoints(fuelEntries), [fuelEntries]);
  const fuelConsumptionMax = useMemo(
    () => Math.max(1, ...fuelConsumptionPoints.map((point) => point.value)),
    [fuelConsumptionPoints]
  );
  const fuelConsumptionAverage = useMemo(() => {
    if (!fuelConsumptionPoints.length) {
      return "";
    }
    const total = fuelConsumptionPoints.reduce((sum, point) => sum + point.value, 0);
    return (total / fuelConsumptionPoints.length).toFixed(2);
  }, [fuelConsumptionPoints]);
  const activeActivityFilterCount = useMemo(
    () => Object.values(filters).filter(Boolean).length,
    [filters]
  );
  const draftOverlapHours = useMemo(
    () => overlapHoursForDraft(activities, draft, editingEntryId),
    [activities, draft, editingEntryId]
  );
  const draftEffectiveHours = useMemo(
    () => (Number(draft.duration_hours || 0) - Number(draftOverlapHours || 0)).toFixed(2),
    [draft.duration_hours, draftOverlapHours]
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

  async function loadFuelVehicles() {
    const response = await apiFetch("/fuel/vehicles");
    const vehicles = await response.json() as FuelVehicle[];
    setFuelVehicles(vehicles);
    const nextSelected = selectedFuelVehicleId || vehicles.find((vehicle) => vehicle.is_active)?.id || vehicles[0]?.id || "";
    setSelectedFuelVehicleId(nextSelected);
    if (nextSelected) {
      setFuelDraft((current) => ({ ...current, vehicle_id: current.vehicle_id || nextSelected }));
      await loadFuelEntries(nextSelected);
    }
  }

  async function loadFuelEntries(vehicleId = selectedFuelVehicleId) {
    if (!vehicleId) {
      setFuelEntries([]);
      return;
    }
    const response = await apiFetch(`/fuel/entries?${buildQuery({ vehicle_id: vehicleId, limit: "5000" })}`);
    setFuelEntries(await response.json());
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
    const requests = [loadActivities(), loadStats(), loadOverheadTickets(), loadCategoryComparison(), loadFuelVehicles()];
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

  useEffect(() => {
    if (editingEntryId) {
      return;
    }
    const latestEnd = activities
      .filter((row) => row.spent_on === draft.spent_on && row.ended_at)
      .sort((left, right) => timeMinutes(right.ended_at) - timeMinutes(left.ended_at))[0];
    const nextPrefix = latestEnd ? `${timeValue(latestEnd.ended_at)}-` : "";
    setTextEntry((current) => (isAutoTimePrefix(current) ? nextPrefix : current));
    setTextEntryRecognized(false);
  }, [activities, draft.spent_on, editingEntryId]);

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
    const nextTextPrefix = !editingEntryId && draft.ended_at ? `${draft.ended_at}-` : "";
    setEditingEntryId(null);
    setDraft({ ...emptyDraft, spent_on: draft.spent_on });
    setTextEntry(nextTextPrefix);
    setTextEntryRecognized(false);
    await Promise.all([loadActivities(), loadStats(), loadCategoryComparison()]);
  }

  async function saveFuelEntry(event: FormEvent) {
    event.preventDefault();
    if (!selectedFuelVehicle?.is_active) {
      setMessage("Pro neaktivni vozidlo nelze pridavat ani upravovat PHM.");
      return;
    }
    if (editingFuelEntryId) {
      const response = await apiFetch(`/fuel/entries/${editingFuelEntryId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...fuelDraft,
          vehicle_id: fuelDraft.vehicle_id,
          purchased_at: fuelDraft.purchased_at || null,
          station: fuelDraft.station || null,
          fuel_type: fuelDraft.fuel_type || null,
          odometer_km: fuelDraft.odometer_km || null,
          liters: fuelDraft.liters || null,
          total_price_vat: fuelDraft.total_price_vat || null,
          total_price_no_vat: fuelDraft.total_price_no_vat || null,
          price_per_liter: fuelDraft.price_per_liter || null,
          trip_km: fuelDraft.trip_km || null,
          full_tank: fuelDraft.full_tank === "" ? null : fuelDraft.full_tank === "true",
          average_consumption: fuelDraft.average_consumption || null,
          note: fuelDraft.note || null
        })
      });
      if (!response.ok) {
        setMessage("Zaznam PHM se nepodarilo upravit.");
        return;
      }
      setMessage("Zaznam PHM upraven.");
    } else {
      const form = new FormData();
      Object.entries(fuelDraft).forEach(([key, value]) => {
        if (value) form.set(key, value);
      });
      if (receiptPhoto) form.set("receipt_photo", receiptPhoto);
      if (dashboardPhoto) form.set("dashboard_photo", dashboardPhoto);
      const response = await apiFetch("/fuel/entries", { method: "POST", body: form });
      if (!response.ok) {
        setMessage("Zaznam PHM se nepodarilo ulozit.");
        return;
      }
      setMessage("Zaznam PHM ulozen.");
    }
    setEditingFuelEntryId(null);
    setReceiptPhoto(null);
    setDashboardPhoto(null);
    setFuelDraft({ ...emptyFuelDraft, vehicle_id: selectedFuelVehicleId, purchased_on: today() });
    await loadFuelEntries(selectedFuelVehicleId);
  }

  async function parseFuelPhotos() {
    if (!receiptPhoto && !dashboardPhoto) {
      setMessage("Vyberte fotku uctenky nebo palubni desky.");
      return;
    }
    const form = new FormData();
    if (receiptPhoto) form.set("receipt_photo", receiptPhoto);
    if (dashboardPhoto) form.set("dashboard_photo", dashboardPhoto);
    setIsParsingFuelPhotos(true);
    try {
      const response = await apiFetch("/fuel/parse-photos", { method: "POST", body: form });
      const result = await response.json();
      if (!response.ok) {
        setMessage(result.detail || "Fotky se nepodarilo rozpoznat.");
        return;
      }
      updateFuelDraft(result.draft);
      setMessage(result.confidence_notes?.join(" ") || "Fotky byly rozpoznany.");
    } finally {
      setIsParsingFuelPhotos(false);
    }
  }

  async function parseTextEntry() {
    if (!textEntry.trim()) {
      setMessage("Zadejte text aktivity k rozpoznani.");
      return;
    }
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
    const nextDraft = {
      ...draft,
      ...parsed.draft,
      category_code: parsed.draft.category_code ?? draft.category_code ?? "",
      reported_status: draft.reported_status
    };
    setDraft(nextDraft);
    const quickText = quickTextFromDraft(nextDraft);
    if (quickText) {
      setTextEntry(quickText);
    }
    setTextEntryRecognized(Boolean(parsed.draft.started_at && parsed.draft.ended_at && parsed.draft.description));
    setMessage(parsed.matched_ticket ? `Vybran tiket ${parsed.matched_ticket.external_id}.` : parsed.confidence_notes.join(" "));
  }

  function handleEntryKeyDown(event: KeyboardEvent<HTMLFormElement>) {
    if (event.key !== "Enter" || event.target instanceof HTMLTextAreaElement) {
      return;
    }
    if (textEntryRecognized) {
      event.preventDefault();
      void saveEntry();
      return;
    }
    if ((event.target as HTMLElement).dataset.quickText === "true") {
      event.preventDefault();
      void parseTextEntry();
    }
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
    setBulkCopyOpen(false);
    await Promise.all([loadActivities(), loadStats(), loadCategoryComparison()]);
  }

  function suggestedBulkCopyDate() {
    if (!activities.length) {
      return today();
    }
    const lastDate = activities.reduce((max, row) => row.spent_on > max ? row.spent_on : max, activities[0].spent_on);
    const latestMinutesOnLastDate = activities
      .filter((row) => row.spent_on === lastDate)
      .map((row) => minutesFromTime(row.ended_at) ?? minutesFromTime(row.started_at))
      .filter((value): value is number => value !== null)
      .reduce((max, value) => Math.max(max, value), -1);
    const earliestSelectedMinutes = selectedActivities
      .map((row) => minutesFromTime(row.started_at) ?? minutesFromTime(row.ended_at))
      .filter((value): value is number => value !== null)
      .reduce((min, value) => Math.min(min, value), Number.POSITIVE_INFINITY);
    if (Number.isFinite(earliestSelectedMinutes) && earliestSelectedMinutes > latestMinutesOnLastDate) {
      return lastDate;
    }
    return addDays(lastDate, 1);
  }

  function openBulkCopy() {
    if (!selectedActivities.length) {
      setMessage("Nejdrive vyberte aktivity ke kopirovani.");
      return;
    }
    setBulkCopyDate(suggestedBulkCopyDate());
    setBulkCopyOpen(true);
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

  function updateDraftDetail(changes: Partial<EntryDraft> | ((current: EntryDraft) => Partial<EntryDraft>), syncText = true) {
    setTextEntryRecognized(false);
    setDraft((current) => {
      const nextChanges = typeof changes === "function" ? changes(current) : changes;
      let next = { ...current, ...nextChanges };
      if (syncText) {
        const quickText = quickTextFromDraft(next);
        setTextEntry(quickText);
        const description = cleanDescriptionFromDraft(next);
        if (description) {
          next = { ...next, description, raw_text: description };
        }
      }
      return next;
    });
  }

  function updateProject(projectName: string) {
    updateDraftDetail((current) => ({
      project_name: projectName,
      category_code: current.category_code || inferredCategory(projectName)
    }));
  }

  function updateDraftTime(field: "started_at" | "ended_at", value: string) {
    updateDraftDetail((current) => {
      const next = { ...current, [field]: value };
      const durationHours = durationFromTimes(next.started_at, next.ended_at);
      return {
        [field]: value,
        duration_hours: durationHours || next.duration_hours
      };
    });
  }

  function copyRow(row: ActivityRow) {
    setEditingEntryId(null);
    const nextDraft = {
      spent_on: row.spent_on,
      started_at: timeValue(row.started_at),
      ended_at: timeValue(row.ended_at),
      duration_hours: row.duration_hours,
      category_code: row.category_code ?? "",
      description: stripTextEntryStructure(row.description, row.project_name ?? ""),
      ticket_external_id: row.ticket_external_id ?? "",
      project_name: row.project_name ?? "",
      transport_name: row.transport_name ?? "",
      km: row.km ?? "",
      reported_status: row.reported_status ?? "",
      raw_text: stripTextEntryStructure(row.description, row.project_name ?? "")
    };
    setDraft(nextDraft);
    setTextEntry(quickTextFromDraft(nextDraft));
    setTextEntryRecognized(false);
    switchSection("activities");
  }

  function editRow(row: ActivityRow) {
    setEditingEntryId(row.id);
    const nextDraft = {
      spent_on: row.spent_on,
      started_at: timeValue(row.started_at),
      ended_at: timeValue(row.ended_at),
      duration_hours: row.duration_hours,
      category_code: row.category_code ?? "",
      description: stripTextEntryStructure(row.description, row.project_name ?? ""),
      ticket_external_id: row.ticket_external_id ?? "",
      project_name: row.project_name ?? "",
      transport_name: row.transport_name ?? "",
      km: row.km ?? "",
      reported_status: row.reported_status ?? "",
      raw_text: stripTextEntryStructure(row.description, row.project_name ?? "")
    };
    setDraft(nextDraft);
    setTextEntry(quickTextFromDraft(nextDraft));
    setTextEntryRecognized(false);
    switchSection("activities");
  }

  function cancelEdit() {
    setEditingEntryId(null);
    setDraft({ ...emptyDraft, spent_on: draft.spent_on });
  }

  async function selectFuelVehicle(vehicleId: string) {
    setSelectedFuelVehicleId(vehicleId);
    setFuelDraft({ ...emptyFuelDraft, vehicle_id: vehicleId, purchased_on: today() });
    setEditingFuelEntryId(null);
    await loadFuelEntries(vehicleId);
  }

  function updateFuelDraft(changes: Partial<FuelDraft>) {
    setFuelDraft((current) => {
      const next = { ...current, ...changes };
      const liters = Number(next.liters || 0);
      const total = Number(next.total_price_vat || 0);
      const pricePerLiter = Number(next.price_per_liter || 0);
      const tripKm = Number(next.trip_km || 0);
      const odometer = Number(next.odometer_km || 0);
      if (liters && pricePerLiter && !changes.total_price_vat) {
        next.total_price_vat = (liters * pricePerLiter).toFixed(2);
      } else if (liters && total && !changes.price_per_liter) {
        next.price_per_liter = (total / liters).toFixed(2);
      }
      if (odometer && !changes.trip_km) {
        const previous = previousFuelEntry(next, editingFuelEntryId);
        if (previous?.odometer_km && odometer > Number(previous.odometer_km)) {
          next.trip_km = (odometer - Number(previous.odometer_km)).toFixed(0);
        }
      }
      const calculatedTripKm = Number(next.trip_km || tripKm || 0);
      if (next.full_tank !== "true") {
        next.average_consumption = "";
      } else if (liters && calculatedTripKm && !changes.average_consumption) {
        const accumulated = accumulatedLitersSinceFull(next, editingFuelEntryId);
        const previousFull = previousFullFuelEntry(next, editingFuelEntryId);
        const kmSinceFull = previousFull?.odometer_km && odometer > Number(previousFull.odometer_km)
          ? odometer - Number(previousFull.odometer_km)
          : calculatedTripKm;
        next.average_consumption = ((accumulated / kmSinceFull) * 100).toFixed(2);
      }
      return next;
    });
  }

  function previousFuelEntry(draftValue: FuelDraft, excludedId: string | null) {
    const currentTime = draftValue.purchased_at || "23:59";
    return [...fuelEntries]
      .filter((entry) => entry.id !== excludedId && entry.odometer_km)
      .filter((entry) => entry.purchased_on < draftValue.purchased_on || (entry.purchased_on === draftValue.purchased_on && (entry.purchased_at || "00:00") < currentTime))
      .sort((left, right) => {
        const dateCompare = right.purchased_on.localeCompare(left.purchased_on);
        if (dateCompare) return dateCompare;
        return (right.purchased_at || "").localeCompare(left.purchased_at || "");
      })[0];
  }

  function previousFullFuelEntry(draftValue: FuelDraft, excludedId: string | null) {
    const currentTime = draftValue.purchased_at || "23:59";
    return [...fuelEntries]
      .filter((entry) => entry.id !== excludedId && entry.full_tank === true && entry.odometer_km)
      .filter((entry) => entry.purchased_on < draftValue.purchased_on || (entry.purchased_on === draftValue.purchased_on && (entry.purchased_at || "00:00") < currentTime))
      .sort((left, right) => {
        const dateCompare = right.purchased_on.localeCompare(left.purchased_on);
        if (dateCompare) return dateCompare;
        return (right.purchased_at || "").localeCompare(left.purchased_at || "");
      })[0];
  }

  function accumulatedLitersSinceFull(draftValue: FuelDraft, excludedId: string | null) {
    const previousFull = previousFullFuelEntry(draftValue, excludedId);
    const currentTime = draftValue.purchased_at || "23:59";
    const previousFullKey = previousFull ? `${previousFull.purchased_on}T${previousFull.purchased_at || "00:00"}` : "";
    const currentKey = `${draftValue.purchased_on}T${currentTime}`;
    const previousLiters = fuelEntries
      .filter((entry) => entry.id !== excludedId && entry.liters)
      .filter((entry) => {
        const key = `${entry.purchased_on}T${entry.purchased_at || "00:00"}`;
        return key > previousFullKey && key < currentKey;
      })
      .reduce((sum, entry) => sum + Number(entry.liters || 0), 0);
    return previousLiters + Number(draftValue.liters || 0);
  }

  function editFuelRow(row: FuelEntry) {
    setEditingFuelEntryId(row.id);
    setFuelDraft({
      vehicle_id: row.vehicle_id,
      purchased_on: row.purchased_on,
      purchased_at: timeValue(row.purchased_at),
      station: row.station ?? "",
      fuel_type: row.fuel_type ?? "",
      odometer_km: row.odometer_km ?? "",
      liters: row.liters ?? "",
      total_price_vat: row.total_price_vat ?? "",
      total_price_no_vat: row.total_price_no_vat ?? "",
      price_per_liter: row.price_per_liter ?? "",
      trip_km: row.trip_km ?? "",
      full_tank: row.full_tank === null ? "" : String(row.full_tank),
      average_consumption: row.average_consumption ?? "",
      note: row.note ?? ""
    });
    setReceiptPhoto(null);
    setDashboardPhoto(null);
  }

  function cancelFuelEdit() {
    setEditingFuelEntryId(null);
    setFuelDraft({ ...emptyFuelDraft, vehicle_id: selectedFuelVehicleId, purchased_on: today() });
    setReceiptPhoto(null);
    setDashboardPhoto(null);
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
              <form className="panel entryPanel" onSubmit={saveEntry} onKeyDownCapture={handleEntryKeyDown}>
                <div className="panelHeader">
                  <h2>{editingEntryId ? "Uprava zaznamu" : "Novy zaznam"}</h2>
                  <Save size={18} />
                </div>

                <div className="quickEntry">
                  <label>Datum<input type="date" value={draft.spent_on} onChange={(e) => updateDraftDetail({ spent_on: e.target.value }, false)} /></label>
                  <label>
                    Text
                    <input
                      data-quick-text="true"
                      value={textEntry}
                      onChange={(event) => {
                        setTextEntry(event.target.value);
                        setTextEntryRecognized(false);
                      }}
                      placeholder="08:00-08:30: E-maily Z: ZAKO SMLS"
                    />
                  </label>
                  <button type="button" onClick={parseTextEntry}>
                    <Search size={18} /> Rozpoznat
                  </button>
                </div>

                <div className="gridForm">
                  <label>Od<input type="time" value={draft.started_at} onChange={(e) => updateDraftTime("started_at", e.target.value)} /></label>
                  <label>Do<input type="time" value={draft.ended_at} onChange={(e) => updateDraftTime("ended_at", e.target.value)} /></label>
                  <label>Hodin<input type="number" step="0.25" value={draft.duration_hours} onChange={(e) => updateDraftDetail({ duration_hours: e.target.value }, false)} /></label>
                  <label>Prekryv<input readOnly value={draftOverlapHours} /></label>
                  <label>Skutecne<input readOnly value={draftEffectiveHours} /></label>
                  <label>Kat.<input value={draft.category_code} onChange={(e) => updateDraftDetail({ category_code: e.target.value }, false)} /></label>
                  <label>Tiket<input value={draft.ticket_external_id} onChange={(e) => updateDraftDetail({ ticket_external_id: e.target.value }, false)} /></label>
                  <label>Zakazka<input value={draft.project_name} onChange={(e) => updateProject(e.target.value)} /></label>
                  <label>Doprava<input list="transport-options" value={draft.transport_name} onChange={(e) => updateDraftDetail({ transport_name: e.target.value }, false)} /></label>
                  <label>km<input type="number" step="0.1" value={draft.km} onChange={(e) => updateDraftDetail({ km: e.target.value }, false)} /></label>
                  <label>Zapsano<input value={draft.reported_status} onChange={(e) => updateDraftDetail({ reported_status: e.target.value }, false)} /></label>
                </div>
                <datalist id="transport-options">
                  {transportOptions.map((transport) => <option key={transport} value={transport} />)}
                </datalist>
                <label>Popis<textarea value={draft.description} onChange={(e) => updateDraftDetail({ description: e.target.value, raw_text: e.target.value }, false)} /></label>
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
                <div className="headerActions">
                  <button type="button" className="secondary" onClick={() => setActivityFiltersOpen((current) => !current)}>
                    <ListFilter size={18} /> Filtr{activeActivityFilterCount ? ` (${activeActivityFilterCount})` : ""}
                  </button>
                  <button type="button" className="secondary" onClick={openBulkCopy}>
                    <CheckSquare size={18} /> Kopie{selectedActivityIds.length ? ` (${selectedActivityIds.length})` : ""}
                  </button>
                  <button type="button" className="secondary" onClick={exportActivities}><Download size={18} /> Excel</button>
                </div>
              </div>
              {activityFiltersOpen && (
                <form className="filterBar" onSubmit={applyFilters}>
                  <label>Od<input type="date" value={filters.date_from} onChange={(e) => setFilters({ ...filters, date_from: e.target.value })} /></label>
                  <label>Do<input type="date" value={filters.date_to} onChange={(e) => setFilters({ ...filters, date_to: e.target.value })} /></label>
                  <label>Zakazka<input value={filters.project} onChange={(e) => setFilters({ ...filters, project: e.target.value })} /></label>
                  <label>Tiket<input value={filters.ticket} onChange={(e) => setFilters({ ...filters, ticket: e.target.value })} /></label>
                  <label>Text<input value={filters.text} onChange={(e) => setFilters({ ...filters, text: e.target.value })} /></label>
                  <button type="submit"><Search size={18} /> Filtrovat</button>
                </form>
              )}
              {bulkCopyOpen && (
                <form className="bulkCopyForm" onSubmit={bulkCopyActivities}>
                  <label>Kopirovat na<input type="date" value={bulkCopyDate} onChange={(event) => setBulkCopyDate(event.target.value)} /></label>
                  <span className="bulkInfo">Vybrano {selectedActivityIds.length}</span>
                  <button type="submit"><CheckSquare size={18} /> Zkopirovat vybrane</button>
                  <button type="button" className="secondary" onClick={() => setBulkCopyOpen(false)}><X size={18} /> Zrusit</button>
                </form>
              )}

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
                            <td className="timeCell timeStart"><span>{timeValue(row.started_at)}</span></td>
                            <td className="timeCell timeEnd"><span>{timeValue(row.ended_at)}</span></td>
                            <td>{row.duration_hours}</td>
                            <td>{formatOverlap(row.overlap_hours)}</td>
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

        {section === "fuel" && (
          <section className="panel widePanel">
            <div className="panelHeader">
              <div>
                <h2>Evidence PHM</h2>
                <p className="muted">Vozidla, tankovani, fotky uctenek a mesicni/rocni mezisoucty.</p>
              </div>
              <div className="actions">
                <button type="button" className="secondary" onClick={() => setFuelStatsOpen((current) => !current)}>
                  <BarChart3 size={18} /> {fuelStatsOpen ? "Skryt statistiku" : "Statistika spotreby"}
                </button>
                <Fuel size={18} />
              </div>
            </div>

            <div className="vehicleTabs">
              {fuelVehicles.map((vehicle) => (
                <button
                  key={vehicle.id}
                  type="button"
                  className={`${selectedFuelVehicleId === vehicle.id ? "active" : ""} ${vehicle.is_active ? "" : "inactive"}`}
                  onClick={() => selectFuelVehicle(vehicle.id)}
                  title={vehicle.is_active ? "Aktivni vozidlo" : "Neaktivni vozidlo jen pro prohlizeni"}
                >
                  {vehicle.name}
                  {!vehicle.is_active && <span>neaktivni</span>}
                </button>
              ))}
            </div>

            {fuelStatsOpen && (
              <div className="chartPanel fuelStatsPanel">
                <div className="chartHeader">
                  <div>
                    <h3>Prubeh spotreby</h3>
                    <p className="muted">Mesicni souhrn spotreby za poslednich {fuelConsumptionPoints.length} mesicu.</p>
                  </div>
                  <strong>{fuelConsumptionAverage ? `${formatNumber(fuelConsumptionAverage)} l/100 km` : ""}</strong>
                </div>
                {fuelConsumptionPoints.length ? (
                  <div className="barChart fuelConsumptionChart" role="img" aria-label="Prubeh prumerne spotreby PHM">
                    {fuelConsumptionPoints.map((point) => {
                      const height = Math.max(3, (point.value / fuelConsumptionMax) * 100);
                      return (
                        <div className="barColumn" key={point.key} title={`${point.key}: ${point.value.toFixed(2)} l/100 km; ${point.tripKm.toFixed(0)} km; ${point.liters.toFixed(2)} l; ${point.entries} cerpani`}>
                          <span className="barValue">{point.value.toFixed(1)}</span>
                          <div className="barTrack">
                            <div className="barFill consumptionFill" style={{ height: `${height}%` }} />
                          </div>
                          <span className="barLabel">{point.label}</span>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <p className="muted">Pro graf zatim nejsou k dispozici vypoctene spotreby.</p>
                )}
              </div>
            )}

            {selectedFuelVehicle && (
              <form className={`fuelForm ${selectedFuelVehicle.is_active ? "" : "disabledPanel"}`} onSubmit={saveFuelEntry}>
                <div className="panelHeader compactHeader">
                  <div>
                    <h3>{editingFuelEntryId ? "Uprava tankovani" : "Nove tankovani"} - {selectedFuelVehicle.name}</h3>
                    {!selectedFuelVehicle.is_active && <p className="muted">Vozidlo je neaktivni, nove zaznamy ani upravy nejsou povolene.</p>}
                  </div>
                  {editingFuelEntryId && <button type="button" className="secondary" onClick={cancelFuelEdit}><X size={18} /> Zrusit</button>}
                </div>
                <fieldset disabled={!selectedFuelVehicle.is_active}>
                  <div className="gridForm fuelGrid">
                    <label>Datum<input type="date" value={fuelDraft.purchased_on} onChange={(e) => updateFuelDraft({ purchased_on: e.target.value })} /></label>
                    <label>Cas<input type="time" value={fuelDraft.purchased_at} onChange={(e) => updateFuelDraft({ purchased_at: e.target.value })} /></label>
                    <label>Cerpaci stanice<input value={fuelDraft.station} onChange={(e) => updateFuelDraft({ station: e.target.value })} /></label>
                    <label>Palivo<input value={fuelDraft.fuel_type} onChange={(e) => updateFuelDraft({ fuel_type: e.target.value })} /></label>
                    <label>Stav km<input type="number" step="1" value={fuelDraft.odometer_km} onChange={(e) => updateFuelDraft({ odometer_km: e.target.value })} /></label>
                    <label>Litru<input type="number" step="0.01" value={fuelDraft.liters} onChange={(e) => updateFuelDraft({ liters: e.target.value })} /></label>
                    <label>Cena s DPH<input type="number" step="0.01" value={fuelDraft.total_price_vat} onChange={(e) => updateFuelDraft({ total_price_vat: e.target.value })} /></label>
                    <label>Cena bez DPH<input type="number" step="0.01" value={fuelDraft.total_price_no_vat} onChange={(e) => updateFuelDraft({ total_price_no_vat: e.target.value })} /></label>
                    <label>Cena/l<input type="number" step="0.01" value={fuelDraft.price_per_liter} onChange={(e) => updateFuelDraft({ price_per_liter: e.target.value })} /></label>
                    <label>Ujeto km<input type="number" step="1" value={fuelDraft.trip_km} onChange={(e) => updateFuelDraft({ trip_km: e.target.value })} /></label>
                    <label>Plna nadrz<select value={fuelDraft.full_tank} onChange={(e) => updateFuelDraft({ full_tank: e.target.value })}><option value="">-</option><option value="true">Ano</option><option value="false">Ne</option></select></label>
                    <label>Spotreba<input type="number" step="0.01" value={fuelDraft.average_consumption} onChange={(e) => updateFuelDraft({ average_consumption: e.target.value })} /></label>
                    {!editingFuelEntryId && <label>Fotka uctenky<input type="file" accept="image/*" onChange={(e) => setReceiptPhoto(e.target.files?.[0] ?? null)} /></label>}
                    {!editingFuelEntryId && <label>Fotka palubky<input type="file" accept="image/*" onChange={(e) => setDashboardPhoto(e.target.files?.[0] ?? null)} /></label>}
                  </div>
                  {!editingFuelEntryId && (
                    <div className="actions">
                      <button type="button" className="secondary" disabled={isParsingFuelPhotos || (!receiptPhoto && !dashboardPhoto)} onClick={parseFuelPhotos}>
                        <Search size={18} /> {isParsingFuelPhotos ? "Rozpoznavam..." : "Rozpoznat fotky"}
                      </button>
                    </div>
                  )}
                  <label>Poznamka<textarea value={fuelDraft.note} onChange={(e) => updateFuelDraft({ note: e.target.value })} /></label>
                  <div className="actions">
                    <button type="submit"><Save size={18} /> {editingFuelEntryId ? "Ulozit zmeny" : "Pridat PHM"}</button>
                  </div>
                </fieldset>
              </form>
            )}

            <div className="tableWrap fuelTable">
              <table>
                <thead>
                  <tr>
                    <th>Datum</th><th>Cas</th><th>Cerpaci stanice</th><th>Palivo</th><th>Stav km</th><th>Litru</th><th>Cena</th><th>Cena/l</th><th>Ujeto</th><th>Plna</th><th>Spotreba</th><th>Zdroj</th><th></th>
                  </tr>
                </thead>
                <tbody>
                  {fuelDisplayRows.map((row) => row.kind === "subtotal" ? (
                    <tr className={`subtotalRow fuelSubtotal ${row.level === "year" ? "yearSubtotal" : ""}`} key={row.key}>
                      <td colSpan={5}>{row.label}</td>
                      <td>{formatNumber(row.liters)}</td>
                      <td>{formatNumber(row.total)}</td>
                      <td></td>
                      <td>{formatKm(row.tripKm)}</td>
                      <td></td>
                      <td><span className={fuelAverageClass(row.average)}>{formatNumber(row.average)}</span></td>
                      <td colSpan={2}></td>
                    </tr>
                  ) : (
                    <tr key={row.entry.id}>
                      <td>{row.entry.purchased_on}</td>
                      <td>{timeValue(row.entry.purchased_at)}</td>
                      <td>{row.entry.station}</td>
                      <td>{row.entry.fuel_type}</td>
                      <td>{formatKm(row.entry.odometer_km)}</td>
                      <td>{formatNumber(row.entry.liters)}</td>
                      <td>{formatNumber(row.entry.total_price_vat)}</td>
                      <td>{formatNumber(row.entry.price_per_liter)}</td>
                      <td>{formatKm(row.entry.trip_km)}</td>
                      <td>{formatBool(row.entry.full_tank)}</td>
                      <td><span className={fuelAverageClass(row.entry.average_consumption)}>{formatNumber(row.entry.average_consumption)}</span></td>
                      <td>{row.entry.source}</td>
                      <td className="rowActions">
                        <button className="iconButton secondary" disabled={!selectedFuelVehicle?.is_active} onClick={() => editFuelRow(row.entry)} title="Upravit PHM"><Edit3 size={16} /></button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
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
