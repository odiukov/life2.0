import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import DashboardPage from "./pages/DashboardPage";
import AgentsPage from "./pages/AgentsPage";
import { ErrorBoundary } from "./components/ErrorBoundary";

const NAV_STYLE: React.CSSProperties = {
  display: "flex",
  gap: "0",
  background: "#13131f",
  borderBottom: "1px solid #1e1e30",
  padding: "0 16px",
};

const LINK_STYLE: React.CSSProperties = {
  padding: "10px 16px",
  fontSize: "12px",
  color: "#666",
  textDecoration: "none",
  fontFamily: "monospace",
};

const ACTIVE_STYLE: React.CSSProperties = {
  ...LINK_STYLE,
  color: "#4a9eff",
  borderBottom: "2px solid #4a9eff",
};

export default function App() {
  return (
    <BrowserRouter>
      <div style={{ background: "#0d0d1a", minHeight: "100vh", color: "#e0e0e0" }}>
        <nav style={NAV_STYLE}>
          <NavLink
            to="/"
            end
            style={({ isActive }) => (isActive ? ACTIVE_STYLE : LINK_STYLE)}
          >
            Dashboard
          </NavLink>
          <NavLink
            to="/agents"
            style={({ isActive }) => (isActive ? ACTIVE_STYLE : LINK_STYLE)}
          >
            Topology
          </NavLink>
        </nav>
        <ErrorBoundary>
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/agents" element={<AgentsPage />} />
          </Routes>
        </ErrorBoundary>
      </div>
    </BrowserRouter>
  );
}
