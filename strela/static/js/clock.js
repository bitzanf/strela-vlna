var secondHand;
var minsHand;
var hourHand;
var timer;

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

    var dst = (soutez_start.getTime() + soutez_len * 60000) - now.getTime();
    if (dst >= 0) {
        var dst_h = Math.floor((dst % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
        var dst_m = Math.floor((dst % (1000 * 60 * 60)) / (1000 * 60));
        var dst_s = Math.floor((dst % (1000 * 60)) / 1000);
        
        var outstr = '';
        if (dst_h > 0) outstr += dst_h + 'h ';
        if (dst_m > 0) outstr += dst_m + 'm ';
        if (dst_s > 0) outstr += dst_s + 's ';
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
    soutez_start = new Date();
    const btn = document.getElementById('startbtn');
    btn.disabled = true;
}

document.addEventListener("DOMContentLoaded", function(event) {
    secondHand = document.querySelector('.second-hand');
    minsHand = document.querySelector('.min-hand');
    hourHand = document.querySelector('.hour-hand');
    timer = document.querySelector('.timer');
    setInterval(updateClock, 1000);
    updateClock();
});