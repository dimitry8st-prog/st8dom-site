const fs = require('fs');
const vm = require('vm');
const path = require('path');
const assert = require('assert');
const code = fs.readFileSync(path.join(__dirname, '../static/js/main.js'), 'utf8');
const block = code.slice(code.indexOf('  function setupProjectNarration'), code.indexOf('  document.querySelectorAll(".case-video video, .project-video-player")'));
class Media {
 constructor(){this.handlers={}; this.attrs={};this.currentTime=0;this.playbackRate=1;this.volume=1;this.paused=true;this.ended=false;this.muted=false;}
 addEventListener(n,f){this.handlers[n]=f;}
 getAttribute(n){return this.attrs[n];} setAttribute(n,v){this.attrs[n]=v;}
 removeAttribute(n){delete this.attrs[n];} load(){} pause(){this.paused=true;} play(){this.paused=false;return Promise.resolve();}
 insertAdjacentElement(_,e){this.button=e;}
 fire(n){this.handlers[n]?.();}
}
let audio;
const ctx={Audio:function(){audio=new Media();return audio;},document:{createElement:()=>new Media()}};
vm.createContext(ctx);vm.runInContext(block,ctx);
const video=new Media();video.attrs['data-clean-voice-src']='clean-one.mp3';ctx.setupProjectNarration(video);
assert(video.muted);assert.equal(audio.src,'clean-one.mp3');
video.paused=false;video.fire('play');assert(!audio.paused);
video.currentTime=14;video.fire('seeked');assert.equal(audio.currentTime,14);
video.playbackRate=1.5;video.fire('ratechange');assert.equal(audio.playbackRate,1.5);
video.paused=true;video.fire('pause');assert(audio.paused);
video.paused=false;video.fire('play');video.button.fire('click');assert(audio.paused);
video.button.fire('click');assert(!audio.paused);
video.muted=false;video.fire('volumechange');assert(video.muted);
video.attrs['data-clean-voice-src']='clean-two.mp3';video.fire('loadstart');assert(audio.paused);assert.equal(audio.src,'clean-two.mp3');
video.attrs['data-clean-voice-src']='';video.fire('loadstart');assert(video.button.hidden);
console.log('Narration sync checked: play, pause, seek, speed, toggle, clip switch; embedded music remains muted.');

video.attrs["data-clean-voice-src"]="clean-three.mp3";video.fire("loadstart");video.paused=false;video.fire("play");video.fire("playing");assert(!audio.paused);video.fire("waiting");assert(audio.paused,"voice must pause while video buffers to avoid repeating words on resync");

video.fire('playing');assert(!audio.paused, 'voice resumes when video plays again');
video.fire('waiting');video.button.fire('click');video.button.fire('click');assert(audio.paused, 'toggle cannot start voice during buffering');
video.fire('playing');assert(!audio.paused);
(async function () {
 let rejectPlay;
 audio.play = function () { this.paused=false; return new Promise((resolve,reject)=>{ rejectPlay=reject; }); };
 video.fire('play');
 video.paused=true;video.fire('pause');
 rejectPlay(Object.assign(new Error('interrupted'), { name: 'AbortError' }));
 await Promise.resolve();
 assert.equal(video.button.attrs['aria-pressed'], 'true', 'interrupted play must not disable narration');
 video.paused=false;video.fire('play');
 const rejectOld=rejectPlay;
 video.attrs['data-clean-voice-src']='next-clip.mp3';video.fire('loadstart');
 rejectOld(new Error('old clip rejected'));
 await Promise.resolve();
 assert.equal(video.button.attrs['aria-pressed'], 'true', 'old clip rejection must not disable new clip');
 console.log('Buffering pauses voice; resume, toggle and stale play rejection checked.');
})().catch(error=>{console.error(error);process.exitCode=1;});
