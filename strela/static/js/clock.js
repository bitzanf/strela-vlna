var secondHand;
var minsHand;
var hourHand;
var timer;
var showSeconds = false;

function updateClock() {
    const now = new Date();

    const seconds = now.getSeconds();
    const secondsDegrees = ((seconds / 60) * 360) + 90;
    secondHand.style.transform = `rotate(${secondsDegrees}deg)`;

    const mins = now.getMinutes();
    const minsDegrees = ((mins / 60) * 360) + ((seconds/60)*6) + 90;
    minsHand.style.transform = `rotate(${minsDegrees}deg)`;

    const hour = now.getHours();
    const hourDegrees = ((hour / 12) * 360) + ((mins/60)*30) + 90;
    hourHand.style.transform = `rotate(${hourDegrees}deg)`;
}

function updateTimer() {
    if (soutez_start == null) {
        timer.innerHTML = 'Soutěž ještě nebyla zahájena';
        return;
    }

    var dst = (soutez_start + soutez_len * 60000) - Date.now();
    if (dst >= 0) {
        var dst_h = Math.floor((dst % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
        var dst_m = Math.floor((dst % (1000 * 60 * 60)) / (1000 * 60));
        if (showSeconds) var dst_s = Math.floor((dst % (1000 * 60)) / 1000);
        
        var outstr = '';
        if (dst_h > 0) outstr += dst_h + 'h ';
        if (dst_m > 0) outstr += dst_m + 'm ';
        if (showSeconds) if (dst_s > 0) outstr += dst_s + 's ';
        timer.innerHTML = outstr;

        if (dst < 15 * 60 * 1000) {
            timer.style.color = 'orange';
        }
        if (dst < 5 * 60 * 1000) {
            timer.style.color = 'red';
        }
    } else {
        timer.innerHTML = 'K O N E C';
        timer.style.color = 'red';
    }
}

function startSoutez() {
    soutez_start = Date.now();
    const btn = document.getElementById('startbtn');
    btn.disabled = true;

    showSeconds = document.getElementById('showSeconds').checked;

    let offset = 0;
    const manualTimeStr = document.getElementById('manualTime').value;
    if (manualTimeStr == "") return;

    const manualTime = new Number(manualTimeStr);
    if (manualTime < 0) offset = 0;
    else if (manualTime > soutez_len) offset = soutez_len;
    else offset = manualTime;

    soutez_start -= (soutez_len - offset) * 60000;
}

function toggleShowSeconds(obj) {
    showSeconds = obj.checked;
}

function fullscreen() {
    const target = document.getElementById('fullscreen_target');
    target.requestFullscreen()
    .then(function() {
        timer.style.color = 'white';
        target.style.cursor = 'none';
    });
}

document.addEventListener("DOMContentLoaded", function(event) {
    secondHand = document.querySelector('.second-hand');
    minsHand = document.querySelector('.min-hand');
    hourHand = document.querySelector('.hour-hand');
    timer = document.querySelector('.timer');

    const updater = function() {updateClock(); updateTimer();};
    setInterval(updater, 1000);
    updater();
});

document.addEventListener('fullscreenchange', function(event) {
    const nazev = document.getElementById('nazev_souteze');
    if (document.fullscreenElement === null) {
        nazev.style.removeProperty('color');
        timer.style.removeProperty('color');
        document.getElementById('fullscreen_target').style.removeProperty('cursor');
    } else {
        nazev.style.color = 'white';
    }
});