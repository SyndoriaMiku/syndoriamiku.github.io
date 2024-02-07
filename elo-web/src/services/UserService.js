import axios from "axios"


const loginUser = (username, password) => {
    return axios.post('https://syndoria.pythonanywhere.com/api/token/', {username, password})
}



export {loginUser}