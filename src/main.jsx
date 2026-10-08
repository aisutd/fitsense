import React from "react";
import { createRoot } from "react-dom/client";
import App from "./app.jsx";
import "./app.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);