import React, { useState } from "react";
import './styles.css';
import './Header.css';
import { Link } from "react-router-dom";
const Header = () => {
    const [isLogged, setIsLogged] = useState(false);

    const handleLogin = () => {
        //Login logic
        setIsLogged(true);
    };

    const handleLogout = () => {
        //Logout logic
        setIsLogged(false);
    }

    return (
        <div className="header">
            <div className="header__logo">
                <img src="" alt="logo" className="logo" />
                {/* Logo source here soon */}
            </div>
            <div className="header__title">
                <h1>Grand Temple Elo Ranking</h1>
            </div>
            <div className="header__login">
                {isLogged ? (
                    <>
                        <Link to="/"><button onClick={handleLogout} className="btn">Logout</button></Link>
                    </>
                    
                ) : (
                    <Link to="/login"><button onClick={handleLogin} className="btn">Login</button></Link>
                )}
            </div>
        </div>
    );
};

export default Header;

