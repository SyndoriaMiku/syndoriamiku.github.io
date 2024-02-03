import React, {useState, useEffect} from "react";
import './styles.css';
import './HomePage.css';
import axios from 'axios';

import AddPlayer from "./AddPlayer";

const HomePage = ({ }) => {
    const [players, setPlayers] = useState([]);
    const [query, setQuery] = useState("");


    useEffect(() => {
        getAllPlayers();
    }, []);


    const fetchPlayer = (query) => {
            axios.get(`https://syndoria.pythonanywhere.com/api/filterPlayers/?query=${query}`)
            .then(response => {
                setPlayers(response.data);
            }) .catch ((error) => {
                console.error("Error fetching players", error);
            });
    };

    const getAllPlayers = () => {
        axios.get('https://syndoria.pythonanywhere.com/api/players/')
        .then(response => {
            setPlayers(response.data);
        }) .catch ((error) => {
            console.error("Error fetching players", error);
        });
    };

    

    const handleEnterDown = (e) => {
        //Check if Enter key is pressed
        if (e.keyCode === 13) {
            fetchPlayer(query);
        }
    };




    return (
        <div className="content" style={{backgroundColor: "#E9EBEE"}}>
            <div id="elo" style={{display: "flex", alignItems: "center"}}>
                <h3 className="title-content">Danh sách người chơi</h3>
            </div>
            <div id="find-box" style={{paddingBottom: "16px"}}>
                <input
                    type="text"
                    id="find-player"
                    className="input input-icon"
                    placeholder="Tìm kiếm người chơi"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={handleEnterDown}
                    />
            </div>
            <div id="player-table">
                <table className="table">
                    <thead>
                        <tr>
                            <td className="text-left sort">ID</td>
                            <td className="text-left sort">Tên người chơi</td>
                            <td className="text-left sort">Elo</td>
                        </tr>
                    </thead>
                    <tbody>
                        {players.map(player => (
                            <tr key={player.id} className="player-row">
                                <td className="text-left">{player.id}</td>
                                <td className="text-left">{player.name}</td>
                                <td className="text-left">{player.elo}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
            <div id="result-box"
            style={{
                display: "flex",
                textAlign: "center",
                height: "56px",
                alignItems: "center",
                justifyContent: "center",
            }}
            >
            </div>
        </div>
        
    );
};

export default HomePage;

