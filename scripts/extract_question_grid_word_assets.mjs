import {spawnSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const clips = [
  {file: 'VID-20260518-WA0000.mp4', start: 1.88, end: 2.16},
  {file: 'VID-20260518-WA0001.mp4', start: 2.32, end: 2.8},
  {file: 'VID-20260518-WA0002.mp4', start: 2.92, end: 3.72},
  {file: 'VID-20260518-WA0004.mp4', start: 2.0, end: 2.32},
  {file: 'VID-20260518-WA0005.mp4', start: 2.36, end: 2.64},
  {file: 'VID-20260518-WA0009.mp4', start: 4.08, end: 4.72},
  {file: 'VID-20260518-WA0010.mp4', start: 0.76, end: 1.52},
  {file: 'VID-20260518-WA0011.mp4', start: 1.68, end: 2.32},
  {file: 'VID-20260518-WA0012.mp4', start: 2.16, end: 2.84},
  {file: 'VID-20260518-WA0013.mp4', start: 2.12, end: 2.64},
  {file: 'VID-20260518-WA0014.mp4', start: 3.48, end: 4.2},
];

const root = process.cwd();
const videoDir = path.join(root, 'footage/selects/closing_question_grid');
const audioDir = path.join(root, 'audio/selects/question_grid_words');
const posterDir = path.join(root, 'assets/closing_question_grid_stills');

fs.mkdirSync(audioDir, {recursive: true});
fs.mkdirSync(posterDir, {recursive: true});

const run = (args) => {
  const result = spawnSync('ffmpeg', args, {stdio: 'inherit'});
  if (result.status !== 0) {
    throw new Error(`ffmpeg failed: ${args.join(' ')}`);
  }
};

for (const clip of clips) {
  const id = path.basename(clip.file, path.extname(clip.file));
  const input = path.join(videoDir, clip.file);
  if (!fs.existsSync(input)) {
    throw new Error(`Missing input video: ${input}`);
  }

  const audioStart = Math.max(0, clip.start - 0.03);
  const audioDuration = Math.max(0.12, clip.end - clip.start + 0.14);
  const posterTime = Math.max(0, clip.end + 0.08);
  const audioOut = path.join(audioDir, `${id}_word.wav`);
  const posterOut = path.join(posterDir, `${id}_poster.jpg`);

  run([
    '-y',
    '-hide_banner',
    '-loglevel',
    'error',
    '-ss',
    String(audioStart),
    '-i',
    input,
    '-t',
    String(audioDuration),
    '-vn',
    '-ac',
    '1',
    '-ar',
    '48000',
    '-af',
    'highpass=f=90,acompressor=threshold=-22dB:ratio=2.8:attack=5:release=80,volume=3.0',
    '-c:a',
    'pcm_s16le',
    audioOut,
  ]);

  run([
    '-y',
    '-hide_banner',
    '-loglevel',
    'error',
    '-ss',
    String(posterTime),
    '-i',
    input,
    '-frames:v',
    '1',
    '-q:v',
    '2',
    posterOut,
  ]);
}

console.log(`Wrote ${clips.length} word audio files to ${audioDir}`);
console.log(`Wrote ${clips.length} poster frames to ${posterDir}`);
