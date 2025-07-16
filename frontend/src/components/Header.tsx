import { useAuth } from "../context/AuthContext";
import OnPremisesButton from "./OnPremisesButton";
import { Link } from "react-router-dom";

function Header() {
    const { user, login, logout } = useAuth();

    return (
        <header className="header">
            {/* Logo */}
            <div className="header-logo">
                <img src="/Mateo.png" alt="Logo" className="logo h-10" />
            </div>

            {/* Botones de autenticación */}
            <div className="header-auth-buttons">
                {user ? (
                    <>
                        {/* Ícono de usuario */}
                        <div className="header-user-icon">
                            <img src="/useer.png" alt="Usuario" className="user-icon" />
                        </div>

                        {/* Botón de acceso a On-Premises */}
                        <OnPremisesButton />

                        {/* Cerrar sesión */}
                        <button
                            className="header-btn"
                            onClick={logout}
                        >
                            Cerrar sesión
                        </button>
                    </>
                ) : (
                    <>
                        <button
                            className="header-btn"
                            onClick={() => login("privileged")}
                        >
                            Administrador
                        </button>
                        <button
                            className="header-btn"
                            onClick={() => login("normal")}
                        >
                            Iniciar sesión
                        </button>
                        <button className="header-btn">
                            Registrarse
                        </button>
                    </>
                )}
            </div>
        </header>
    );
}

export default Header;
