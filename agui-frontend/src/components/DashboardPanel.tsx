import type { HealthSummary } from "../types";

const DAY_LETTERS = ["S", "M", "T", "W", "T", "F", "S"];

function sectionLabel(text: string) {
  return (
    <div style={{ color: "#555", fontSize: 9, textTransform: "uppercase", letterSpacing: 1, marginBottom: 8 }}>
      {text}
    </div>
  );
}

function MetricRow({ label, value, unit, color = "#ddd" }: { label: string; value?: number | null; unit?: string; color?: string }) {
  if (value == null) return null;
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", padding: "3px 0" }}>
      <span style={{ color: "#666", fontSize: 10 }}>{label}</span>
      <span style={{ color, fontSize: 12, fontWeight: "bold" }}>
        {value}{unit && <span style={{ fontSize: 9, color: "#888", marginLeft: 2 }}>{unit}</span>}
      </span>
    </div>
  );
}

function MiniBarChart({
  values,
  color,
  label,
  unit,
}: {
  values: number[];
  color: string;
  label: string;
  unit: string;
}) {
  const maxVal = Math.max(1, ...values);
  const today = new Date();
  const dayLabels = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(today);
    d.setDate(today.getDate() - (6 - i));
    return DAY_LETTERS[d.getDay()];
  });

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 3 }}>
        <span style={{ color, fontSize: 9 }}>{label}</span>
        <span style={{ color: "#555", fontSize: 9 }}>
          {values[values.length - 1] > 0 ? `${values[values.length - 1]} ${unit}` : "—"}
        </span>
      </div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 28 }}>
        {values.map((val, i) => (
          <div
            key={i}
            title={`${dayLabels[i]}: ${val} ${unit}`}
            style={{
              background: val > 0 ? color : "#1e1e30",
              flex: 1,
              height: `${Math.max(val > 0 ? 15 : 5, (val / maxVal) * 100)}%`,
              borderRadius: "2px 2px 0 0",
              opacity: i === values.length - 1 ? 1 : 0.55,
            }}
          />
        ))}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", color: "#333", fontSize: 8, marginTop: 2 }}>
        {dayLabels.map((d, i) => <span key={i}>{d}</span>)}
      </div>
    </div>
  );
}

function SleepPhaseBar({ deep, rem, light }: { deep?: number; rem?: number; light?: number }) {
  const total = (deep ?? 0) + (rem ?? 0) + (light ?? 0);
  if (total === 0) return null;
  return (
    <div>
      <div style={{ display: "flex", height: 6, borderRadius: 3, overflow: "hidden", gap: 1, marginTop: 6 }}>
        <div style={{ flex: deep ?? 0, background: "#4a9eff", opacity: 0.9 }} title={`Deep: ${deep}h`} />
        <div style={{ flex: rem ?? 0, background: "#9b59b6", opacity: 0.9 }} title={`REM: ${rem}h`} />
        <div style={{ flex: light ?? 0, background: "#2ecc71", opacity: 0.6 }} title={`Light: ${light}h`} />
      </div>
      <div style={{ display: "flex", gap: 10, marginTop: 4, fontSize: 9, color: "#555" }}>
        <span><span style={{ color: "#4a9eff" }}>■</span> Deep {deep}h</span>
        <span><span style={{ color: "#9b59b6" }}>■</span> REM {rem}h</span>
        <span><span style={{ color: "#2ecc71" }}>■</span> Light {light}h</span>
      </div>
    </div>
  );
}

interface Props {
  summary: HealthSummary | null;
  expandedMetric?: string | null;
}

export function DashboardPanel({ summary, expandedMetric: _expandedMetric }: Props) {
  if (!summary) {
    return (
      <div style={{ padding: 16, color: "#555", fontSize: 11, fontFamily: "monospace" }}>Loading...</div>
    );
  }

  const { body, sleep, daily, trends, recommendation } = summary;

  return (
    <div style={{
      width: 260,
      minWidth: 260,
      background: "#13131f",
      borderRight: "1px solid #1e1e30",
      overflowY: "auto",
      padding: 16,
      display: "flex",
      flexDirection: "column",
      gap: 16,
      fontFamily: "monospace",
    }}>

      {/* BODY COMPOSITION */}
      {body && (
        <div>
          {sectionLabel("My stats")}
          <div style={{ background: "#1a1a2e", borderRadius: 6, padding: "10px 12px" }}>
            <MetricRow label="Weight" value={body.weight_kg} unit="kg" color="#fff" />
            <MetricRow label="Body fat" value={body.body_fat_pct} unit="%" color="#ffb74a" />
            <MetricRow label="Lean mass" value={body.lean_mass_kg} unit="kg" color="#4eff9a" />
            <MetricRow label="BMI" value={body.bmi} color="#ddd" />
            {daily && (
              <>
                <div style={{ height: 1, background: "#1e1e30", margin: "6px 0" }} />
                <MetricRow label="Resting HR" value={daily.resting_hr} unit="bpm" color="#e57373" />
                <MetricRow label="Body battery" value={daily.body_battery_max} unit="%" color="#4a9eff" />
              </>
            )}
          </div>
        </div>
      )}

      {/* LAST NIGHT SLEEP */}
      {sleep && (
        <div>
          {sectionLabel("Last night")}
          <div style={{ background: "#1a1a2e", borderRadius: 6, padding: "10px 12px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: 20, fontWeight: "bold", color: "#4a9eff" }}>
                {sleep.duration_hours}h
              </span>
              {sleep.score != null && (
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontSize: 9, color: "#555" }}>score</div>
                  <div style={{ fontSize: 16, fontWeight: "bold", color: sleep.score >= 80 ? "#4eff9a" : sleep.score >= 60 ? "#ffb74a" : "#e57373" }}>
                    {sleep.score}
                  </div>
                </div>
              )}
            </div>
            {sleep.hrv != null && (
              <div style={{ fontSize: 9, color: "#666", marginTop: 4 }}>HRV avg: <span style={{ color: "#4a9eff" }}>{sleep.hrv}</span></div>
            )}
            <SleepPhaseBar deep={sleep.deep_hours} rem={sleep.rem_hours} light={sleep.light_hours} />
          </div>
        </div>
      )}

      {/* TODAY */}
      {daily && (
        <div>
          {sectionLabel("Today")}
          <div style={{ background: "#1a1a2e", borderRadius: 6, padding: "10px 12px" }}>
            {daily.steps != null && (
              <MetricRow label="Steps" value={daily.steps} color="#4a9eff" />
            )}
            {daily.calories_active != null && (
              <MetricRow label="Active kcal" value={daily.calories_active} unit="kcal" color="#ffb74a" />
            )}
            {daily.stress_avg != null && (
              <MetricRow label="Avg stress" value={daily.stress_avg} color={daily.stress_avg < 40 ? "#4eff9a" : daily.stress_avg < 60 ? "#ffb74a" : "#e57373"} />
            )}
          </div>
        </div>
      )}

      {/* WEEKLY TRENDS */}
      <div>
        {sectionLabel("This week")}
        <div style={{ background: "#1a1a2e", borderRadius: 6, padding: 10, display: "flex", flexDirection: "column", gap: 12 }}>
          <MiniBarChart values={trends.sleep_hours} color="#4a9eff" label="Sleep" unit="h" />
          <MiniBarChart values={trends.workout_minutes} color="#4eff9a" label="Workout" unit="min" />
          <MiniBarChart values={trends.nutrition_calories} color="#ffb74a" label="Nutrition" unit="kcal" />
        </div>
      </div>

      {/* LAST RECOMMENDATION */}
      {recommendation && (
        <div>
          {sectionLabel("Last recommendation")}
          <div style={{ background: "#1a1a2e", borderRadius: 6, padding: "10px 12px" }}>
            <div style={{ fontSize: 9, color: "#555", marginBottom: 4 }}>
              {recommendation.agent} · {new Date(recommendation.created_at).toLocaleDateString([], { month: "short", day: "numeric" })}
            </div>
            <div style={{ fontSize: 10, color: "#aaa", lineHeight: 1.5, whiteSpace: "pre-wrap" }}>
              {recommendation.text}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
