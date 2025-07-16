import { Routes, Route, useNavigate } from "react-router-dom";
import Chat from "./components/Chat";
import OnPremiseChat from "./components/OnPremiseChat";
import "./App.css";
import { useState } from "react";

function App() {
  const navigate = useNavigate();
  const [activeChat, setActiveChat] = useState<"claude" | "onpremise">("claude");

  const handleChatToggle = (chat: "claude" | "onpremise") => {
    setActiveChat(chat);
    navigate(chat === "claude" ? "/" : "/onpremises");
  };

  return (
    <div className="app-container">
      {/* Este botón sigue funcionando si quieres mantenerlo también */}
      <div className="chat-selector">
        <button
          className="chat-toggle-btn"
          onClick={() => handleChatToggle(activeChat === "claude" ? "onpremise" : "claude")}
        >
          {activeChat === "claude" ? "Chat On-Premise" : "Chat Claude"}
        </button>
      </div>

      <Routes>
        <Route
          path="/"
          element={<Chat onBotonClick={() => handleChatToggle("onpremise")} />}
        />
        <Route
          path="/onpremises"
          element={<OnPremiseChat onSwitchToClaude={() => handleChatToggle("claude")} />}
        />
      </Routes>
    </div>
  );
}

export default App;
