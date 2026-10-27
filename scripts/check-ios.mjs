import { spawnSync } from "node:child_process";
const staff = process.argv[2] === "staff";
const result = spawnSync(
  "xcodebuild",
  [
    "-project",
    staff ? "ios-staff/App/App.xcodeproj" : "ios/App/App.xcodeproj",
    "-scheme",
    "App",
    "-configuration",
    "Debug",
    "-sdk",
    "iphonesimulator",
    "-destination",
    "generic/platform=iOS Simulator",
    "-derivedDataPath",
    staff ? "output/ios-staff-build" : "output/ios-build",
    "CODE_SIGNING_ALLOWED=NO",
    "build",
  ],
  { stdio: "inherit" },
);
process.exitCode = result.status ?? 1;
