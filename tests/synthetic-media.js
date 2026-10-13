// Only served by browser_flow_server.py on its loopback acceptance fixture.
// Real browser codecs and recording APIs, without physical mic/camera access.
const audio = new AudioContext();
const oscillator = audio.createOscillator();
const gain = audio.createGain();
const destination = audio.createMediaStreamDestination();
oscillator.frequency.value = 220;
gain.gain.value = 0.02;
oscillator.connect(gain).connect(destination);
oscillator.start();
const canvas = document.createElement("canvas");
canvas.width = 320;
canvas.height = 240;
const paint = canvas.getContext("2d");
paint.fillStyle = "#edf0e7";
paint.fillRect(0, 0, 320, 240);
paint.fillStyle = "#23372d";
paint.font = "20px sans-serif";
paint.fillText("Тестовая камера", 70, 125);
const camera = canvas.captureStream(2);
let micRequests = 0, cameraRequests = 0;
Object.defineProperty(navigator.mediaDevices, "getUserMedia", {
  configurable: true,
  value: async ({ audio: withAudio, video: withVideo }) => {
    await audio.resume();
    const tracks = [];
    if (withAudio) {
      micRequests++;
      tracks.push(destination.stream.getAudioTracks()[0].clone());
    }
    if (withVideo) {
      cameraRequests++;
      tracks.push(camera.getVideoTracks()[0].clone());
    }
    document.body.dataset.syntheticMicRequests = String(micRequests);
    document.body.dataset.syntheticCameraRequests = String(cameraRequests);
    return new MediaStream(tracks);
  },
});
