import type { PropsWithChildren } from "react";

import styles from "./AppShell.module.css";

export default function AppShell({ children }: PropsWithChildren) {
  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <div className={styles.brand} aria-label="PNW student support">
          <span className={styles.brandMark}>PNW</span>
          <span className={styles.brandText}>Student Support</span>
        </div>

        <nav className={styles.nav} aria-label="Main navigation">
          <a href="/" className={styles.link}>
            Chat
          </a>
        </nav>
      </header>

      <div className={styles.page}>{children}</div>
    </div>
  );
}
