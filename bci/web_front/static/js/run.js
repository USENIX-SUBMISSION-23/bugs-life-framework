"use strict";

let socket = io();
let log_div;

window.addEventListener('load', function(event) {
    log_div = document.getElementById("log_div");

    socket.emit("ready");
});

socket.on('log', function(args) {
        log(args["message"]);
    });


function show(div_id) {
    document.getElementById(div_id).style.display = "inline-block";
}

function hide(div_id) {
    document.getElementById(div_id).style.display = "none";
}

function search_stategy_click(radio) {
    if (radio.value == "bin_seq") {
        hide("search_stategy_hidden_options");
    } else if (radio.value == "bin_search" || radio.value == "comp_search") {
        show("search_stategy_hidden_options");
    }
}

function run() {

}

function log(message) {
    let p = document.createElement("p");
    p.textContent = message;
    if (message.includes("ERROR")) {
        p.className = "error";
    }
    log_div.appendChild(p);
}