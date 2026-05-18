#!/usr/bin/env node
import {execFileSync} from 'node:child_process';
import {mkdirSync, readdirSync, readFileSync, writeFileSync} from 'node:fs';
import path from 'node:path';

const inputDir = process.argv[2];
const outputDir = process.argv[3] ?? 'analysis/transcripts/chirp2/question_grid_20260518';

if (!inputDir) {
  console.error('Usage: node scripts/chirp2_question_grid.mjs <video-dir> [output-dir]');
  process.exit(1);
}

const projectNumber = process.env.CHIRP_PROJECT_NUMBER ?? '580184833052';
const location = process.env.CHIRP_LOCATION ?? 'asia-southeast1';
const recognizer = process.env.CHIRP_RECOGNIZER ?? 'previllage-ne-chirp2';
const bucket = process.env.CHIRP_BUCKET ?? 'agentshakti-tts-batch';
const gcsPrefix = process.env.CHIRP_GCS_PREFIX ?? 'previllage/chirp2/question_grid_20260518/audio';
const endpoint = `https://${location}-speech.googleapis.com/v2/projects/${projectNumber}/locations/${location}/recognizers/${recognizer}:batchRecognize`;
const operationBase = `https://${location}-speech.googleapis.com/v2/`;

const run = (cmd, args, opts = {}) =>
  execFileSync(cmd, args, {stdio: opts.capture ? ['ignore', 'pipe', 'pipe'] : 'inherit', encoding: opts.capture ? 'utf8' : undefined});

const secondsFromOffset = (value) => {
  if (!value) return 0;
  return Number(String(value).replace(/s$/, ''));
};

const videos = readdirSync(inputDir)
  .filter((name) => /\.(mp4|mov|m4v)$/i.test(name))
  .sort()
  .map((name) => ({
    name,
    stem: name.replace(/\.[^.]+$/, ''),
    path: path.join(inputDir, name),
  }));

if (videos.length === 0) {
  throw new Error(`No videos found in ${inputDir}`);
}

mkdirSync(outputDir, {recursive: true});
mkdirSync(path.join(outputDir, 'audio'), {recursive: true});
mkdirSync(path.join(outputDir, 'per_video'), {recursive: true});

for (const video of videos) {
  video.audio = path.join(outputDir, 'audio', `${video.stem}.flac`);
  video.gcs = `gs://${bucket}/${gcsPrefix}/${video.stem}.flac`;
  run('ffmpeg', ['-y', '-i', video.path, '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'flac', video.audio], {capture: true});
  run('gcloud', ['storage', 'cp', video.audio, video.gcs], {capture: true});
}

const token = run('gcloud', ['auth', 'print-access-token'], {capture: true}).trim();
const allRows = [];
const summary = [];
const mergedRaw = {operations: []};

for (const video of videos) {
  const request = {
    config: {
      autoDecodingConfig: {},
      languageCodes: ['ne-NP'],
      model: 'chirp_2',
      features: {
        enableWordTimeOffsets: true,
        enableAutomaticPunctuation: true,
      },
    },
    files: [{uri: video.gcs}],
    recognitionOutputConfig: {inlineResponseConfig: {}},
  };
  const requestPath = path.join(outputDir, `chirp2_batch_request_${video.stem}.json`);
  writeFileSync(requestPath, JSON.stringify(request, null, 2));
  const startResponse = JSON.parse(
    run(
      'curl',
      ['-sS', '-X', 'POST', '-H', `Authorization: Bearer ${token}`, '-H', 'Content-Type: application/json', endpoint, '-d', `@${requestPath}`],
      {capture: true},
    ),
  );
  writeFileSync(path.join(outputDir, `chirp2_operation_start_${video.stem}.json`), JSON.stringify(startResponse, null, 2));

  if (startResponse.error) {
    throw new Error(`Chirp2 start failed for ${video.name}: ${JSON.stringify(startResponse.error)}`);
  }

  const operationName = startResponse.name;
  writeFileSync(path.join(outputDir, `chirp2_operation_name_${video.stem}.txt`), `${operationName}\n`);

  let operation;
  for (let attempt = 0; attempt < 60; attempt++) {
    operation = JSON.parse(
      run('curl', ['-sS', '-H', `Authorization: Bearer ${token}`, `${operationBase}${operationName}`], {capture: true}),
    );
    if (operation.done) break;
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 2000);
  }

  if (!operation?.done) {
    throw new Error(`Chirp2 operation did not finish for ${video.name}: ${operationName}`);
  }
  if (operation.error) {
    throw new Error(`Chirp2 operation failed for ${video.name}: ${JSON.stringify(operation.error)}`);
  }

  mergedRaw.operations.push({video: video.name, operationName, response: operation});
  writeFileSync(path.join(outputDir, `chirp2_raw_response_${video.stem}.json`), JSON.stringify(operation, null, 2));

  const results = operation.response?.results ?? {};
  const result = results[video.gcs];
  const transcriptResults = result?.inlineResult?.transcript?.results ?? result?.transcript?.results ?? [];
  const words = [];
  const transcript = [];
  for (const segment of transcriptResults) {
    const alternative = segment.alternatives?.[0];
    if (!alternative) continue;
    if (alternative.transcript) transcript.push(alternative.transcript);
    for (const word of alternative.words ?? []) {
      words.push({
        start: secondsFromOffset(word.startOffset ?? word.start_offset),
        end: secondsFromOffset(word.endOffset ?? word.end_offset),
        text: word.word,
      });
    }
  }
  const videoOut = path.join(outputDir, 'per_video', video.stem);
  mkdirSync(videoOut, {recursive: true});
  writeFileSync(path.join(videoOut, 'chirp2_transcript_ne.txt'), `${transcript.join('\n')}\n`);
  writeFileSync(path.join(videoOut, 'chirp2_words.json'), JSON.stringify(words, null, 2));
  writeFileSync(
    path.join(videoOut, 'chirp2_word_beats.tsv'),
    ['start\tend\ttext\tvideo', ...words.map((word) => `${word.start.toFixed(3)}\t${word.end.toFixed(3)}\t${word.text}\t${video.name}`)].join('\n') + '\n',
  );
  summary.push({
    video: video.name,
    path: video.path,
    gcs: video.gcs,
    transcript: transcript.join(' '),
    wordCount: words.length,
    words,
  });
  for (const word of words) {
    allRows.push(`${video.name}\t${word.start.toFixed(3)}\t${word.end.toFixed(3)}\t${word.text}`);
  }
}

writeFileSync(path.join(outputDir, 'chirp2_raw_response.json'), JSON.stringify(mergedRaw, null, 2));
writeFileSync(path.join(outputDir, 'question_grid_transcripts.json'), JSON.stringify(summary, null, 2));
writeFileSync(path.join(outputDir, 'question_grid_word_beats.tsv'), ['video\tstart\tend\ttext', ...allRows].join('\n') + '\n');

console.log(`Wrote ${summary.length} transcripts to ${outputDir}`);
