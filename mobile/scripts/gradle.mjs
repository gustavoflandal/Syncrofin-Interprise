#!/usr/bin/env node
// Runs the Gradle wrapper of the Android project, on Windows or Linux/macOS.
//   node scripts/gradle.mjs assembleDebug
import { spawnSync } from 'node:child_process'
import path from 'node:path'

const android = path.join(import.meta.dirname, '..', 'android')
const windows = process.platform === 'win32'
// On Windows a .bat needs a shell, and cmd does not look in the working directory: use the full,
// quoted path (the repository may live in a folder with spaces).
const wrapper = windows ? `"${path.join(android, 'gradlew.bat')}"` : path.join(android, 'gradlew')
const result = spawnSync(wrapper, process.argv.slice(2), { cwd: android, stdio: 'inherit', shell: windows })
if (result.error) {
  // spawnSync reports "could not even start it" here, with a null status: without this the script exited 1 in
  // silence (on Linux: gradlew not executable), which is exactly how the first CI run failed.
  console.error(`could not run ${wrapper}: ${result.error.message}`)
}
process.exit(result.status ?? 1)
