import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import "../App.css";

const OnPremisesButton = () => {
  const { user } = useAuth();
  const location = useLocation();

  if (user?.role !== "privileged") return null;

  const isInClaudeChat = location.pathname === "/chat";

  return (
    <Link to={isInClaudeChat ? "/" : "/chat"}>
      <button className="header-btn">
        {isInClaudeChat ? "Volver al inicio" : "Chat Claude"}
      </button>
    </Link>
  );
};

export default OnPremisesButton;
