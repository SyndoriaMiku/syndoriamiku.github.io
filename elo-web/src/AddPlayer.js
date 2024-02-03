import React, { useState, useEffect } from "react";
import axios from "axios";

const AddPlayer = ({ isOpen, onClose, reload}) => {
    const [playerId, setPlayerId] = useState("");
    const [playerName, setPlayerName] = useState("");

    useEffect(() => {
        //Fetch automatic new ID when dialog is opened
        axios.get('https://syndoria.pythonanywhere.com/api/new/').then(response => {
            setPlayerId(response.data.id);
        })
        .catch(error => {
            console.error("Error fetching new ID", error);
        });
    }, []); //Empty dependency means this effect will run once when the component is mounted


    const handleSavePlayer = () => {
        //Build JSON object
        const player = {
            id: playerId,
            name: playerName,
            elo: "500.0"
        };

        // Post data to API
        axios.post('https://syndoria.pythonanywhere.com/api/players/', player, {
            headers: {
                'Content-Type': 'application/json'
            },
        }).then(response => {
            //Close dialog
            onClose();

            //Reload table
            reload();
        }
        ).catch(error => {
            console.error("Error saving player", error);
        });
    };

    const handleCancelAddPlayer = () => {
        onClose();
    };



    return (
        <div className="dialog" id="player-dialog">
            <div className="dialog-main" style={{ width: "500px", height: "200px" }}>
                <div className="dialog-title">
                    <h1 className="title-dialog">Thông tin người chơi</h1>
                </div>
                <div className="dialog-form">
                    <div className="row field-row">
                        <div className="col-50">
                            <label htmlFor="player-id" className="title-field">ID</label>
                            <input type="text" id="player-id-input" className="input dialog-input" disabled value={playerId} onChange={(e) => setPlayerId(e.target.value)}/>
                        </div>
                        <div className="col-50">
                            <label htmlFor="player-name" className="title-field">Tên</label>
                            <input type="text" id="player-name-input" className="input dialog-input" value={playerName} onChange={(e) => setPlayerName(e.target.value)}/>
                        </div>
                    </div>
                </div>
                <div className="dialog-footer">
                    <button
                    className="btn btn-dialog"
                    onClick={handleCancelAddPlayer}
                    style={{
                        float: "left",
                        left: "24px",
                    }}>
                        Hủy
                    </button>
                    <button
                    className="btn btn-icon btn-dialog"
                    onClick={handleSavePlayer}
                    style={{
                        backgroundImage: "url(../static/save.png)",
                        float: "right",
                        right: "24px",
                    }}
                    >
                        Lưu
                    </button>
                </div>
            </div>
        </div>
    );
};

export default AddPlayer;