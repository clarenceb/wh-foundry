import ChatWidget from '../components/ChatWidget';
import styles from './WidgetPage.module.css';

export default function WidgetPage() {
  return (
    <div className={styles.page}>
      {/* Simulated WH nav */}
      <nav className={styles.nav}>
        <div className={styles.navLogo}>🏥 Western Health</div>
        <div className={styles.navLinks}>
          <a href="#">Patients &amp; Visitors</a>
          <a href="#">Services</a>
          <a href="#">Locations</a>
          <a href="#">Emergency</a>
          <a href="/">Full Chat App →</a>
        </div>
      </nav>

      {/* Hero */}
      <div className={styles.hero}>
        <h1>Welcome to Western Health</h1>
        <p>
          Providing exceptional and forward-thinking care for patients across
          Melbourne's west. Use our chat assistant for instant help.
        </p>
      </div>

      {/* Placeholder content */}
      <div className={styles.content}>
        <div className={styles.cards}>
          <div className={styles.card}>
            <h3>📍 Our Locations</h3>
            <p>
              Footscray Hospital, Sunshine Hospital, Williamstown Hospital,
              and Sunbury Day Hospital — serving communities across the western suburbs.
            </p>
          </div>
          <div className={styles.card}>
            <h3>🕐 Visiting Hours</h3>
            <p>
              General visiting hours are 12 pm to 8 pm daily.
              Please check specific ward guidelines before your visit.
            </p>
          </div>
          <div className={styles.card}>
            <h3>🚑 Emergency</h3>
            <p>
              For life-threatening emergencies call 000. Our Emergency Departments
              are open 24 hours at Footscray and Sunshine Hospitals.
            </p>
          </div>
          <div className={styles.card}>
            <h3>💬 Patient Chat</h3>
            <p>
              Click the chat bubble in the bottom-right corner to ask questions
              about our services, locations, transport, and more.
            </p>
          </div>
        </div>
      </div>

      {/* The floating chat widget */}
      <ChatWidget />
    </div>
  );
}
