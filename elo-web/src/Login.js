import React, { useState } from 'react'
import './services/UserService.js';
import { loginUser } from "./services/UserService.js";


const Login = ({ }) => {

    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");


    const handleLogin = async () => {
        

        let res = loginUser("username", "password");
    }






    return (
        <div className="content">
            <div className="login">
                <div className="login__title">
                    <h2>Đăng nhập tài khoản admin</h2>
                </div>
                <div className="login__form">
                    <div className="text-input">
                        <label htmlFor="username">Tên đăng nhập</label>
                        <input type="text" id="username" name="username" placeholder="Username" />
                    </div>
                    <div className="text-input">
                        <label htmlFor="password">Mật khẩu</label>
                        <input type="password" id="password" name="password" placeholder="password" />
                    </div>
                </div>
                <div className="login__button">
                    <button className="btn" onClick={() => handleLogin() }>Đăng nhập</button>
                </div>
            </div>
        </div>
    );
};

export default Login;