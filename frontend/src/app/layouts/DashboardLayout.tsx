import { NavLink, Outlet } from "react-router-dom";

import Button from "@/components/core/Button";
import {
  IconFile,
  IconGrade,
  IconHistory,
  IconLayers,
  IconPlus,
  IconScan,
  IconText,
} from "@/components/core/Icon";
import ThemeToggle from "@/components/core/ThemeToggle";
import { useServiceHealth, type HealthState } from "@/hooks/useServiceHealth";
import JobHistorySidebar from "@/modules/grading/JobHistorySidebar";

import styles from "./DashboardLayout.module.css";

const NAV_SECTIONS = [
  {
    title: "Chấm điểm",
    items: [
      { to: "/pipeline", label: "Chấm cả lớp từ ảnh", icon: <IconLayers size={16} />, end: true },
      { to: "/", label: "Chấm từ file JSON", icon: <IconGrade size={16} />, end: true },
    ],
  },
  {
    title: "Chuẩn bị",
    items: [
      { to: "/barem", label: "Soạn barem", icon: <IconFile size={16} />, end: true },
    ],
  },
  {
    title: "Pipeline OCR",
    items: [
      { to: "/ocr/roi", label: "Module 1 · Phát hiện vùng", icon: <IconScan size={16} />, end: false },
      { to: "/ocr/align", label: "Module 2 · Căn chỉnh ảnh", icon: <IconLayers size={16} />, end: false },
      { to: "/ocr/text", label: "Module 3 · Nhận dạng chữ", icon: <IconText size={16} />, end: false },
    ],
  },
];

function healthLabel(state: HealthState): string {
  if (state === "up") return "Đang chạy";
  if (state === "down") return "Không kết nối";
  return "Đang kiểm tra…";
}

function ServiceRow({ name, port, state }: { name: string; port: number; state: HealthState }) {
  return (
    <div className={styles.serviceRow} title={`${name} — ${healthLabel(state)} (cổng ${port})`}>
      <span className={`${styles.serviceDot} ${styles[state]}`} />
      <span className={styles.serviceName}>{name}</span>
      <span className={styles.servicePort}>:{port}</span>
    </div>
  );
}

export default function DashboardLayout() {
  const health = useServiceHealth();

  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar}>
        <div className={styles.brand}>
          <span className={styles.brandMark}>AG</span>
          <span className={styles.brandText}>
            <span className={styles.brandTitle}>Autograding 2026</span>
            <span className={styles.brandSubtitle}>MMLAB · IT001</span>
          </span>
        </div>

        <div className={styles.cta}>
          <Button to="/pipeline" block icon={<IconPlus size={15} />}>
            Phiên chấm mới
          </Button>
        </div>

        <nav className={styles.nav}>
          {NAV_SECTIONS.map((section) => (
            <div key={section.title} className={styles.navSection}>
              <div className={styles.navTitle}>{section.title}</div>
              {section.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    `${styles.navLink} ${isActive ? styles.navLinkActive : ""}`
                  }
                >
                  <span className={styles.navIcon}>{item.icon}</span>
                  {item.label}
                </NavLink>
              ))}
            </div>
          ))}

          <div className={`${styles.navSection} ${styles.historySection}`}>
            <div className={styles.navTitle}>
              <IconHistory size={13} />
              Lịch sử chấm
            </div>
            <JobHistorySidebar />
          </div>
        </nav>

        <footer className={styles.footer}>
          <div className={styles.services}>
            <ServiceRow name="Backend" port={8000} state={health.api} />
            {health.api === "up" && health.llmConfigured === false && (
              <div className={styles.warning}>Chưa cấu hình LLM trong .env — OCR và chấm điểm đều không chạy được</div>
            )}
          </div>
          <ThemeToggle />
        </footer>
      </aside>

      <div className={styles.main}>
        <div className={styles.mainInner}>
          <Outlet />
        </div>
      </div>
    </div>
  );
}
