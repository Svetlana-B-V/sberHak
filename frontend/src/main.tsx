import React from "react";
import ReactDOM from "react-dom/client";
import type { ReactNode } from "react";
import App from "./App";
import "./styles.css";

class AppBoundary extends React.Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    if (this.state.failed)
      return (
        <main className="panel empty-state">
          <h1>Не удалось показать рабочее пространство</h1>
          <p>
            Проекты сохраняются на сервере. Перезагрузите страницу, чтобы
            открыть последнюю сохранённую версию.
          </p>
          <button className="button primary" onClick={() => location.reload()}>
            Перезагрузить страницу
          </button>
        </main>
      );
    return this.props.children;
  }
}
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AppBoundary>
      <App />
    </AppBoundary>
  </React.StrictMode>,
);
