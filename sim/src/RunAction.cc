#include "RunAction.hh"

#include "config.hh"

#include "G4Exception.hh"
#include "G4ExceptionSeverity.hh"
#include "G4Run.hh"

#include <filesystem>
#include <string>

namespace {
bool WritesCsv(Config::OutputFormat mode) {
  return mode == Config::OutputFormat::kCsv ||
         mode == Config::OutputFormat::kBoth;
}

bool WritesHdf5(Config::OutputFormat mode) {
  return mode == Config::OutputFormat::kHdf5 ||
         mode == Config::OutputFormat::kBoth;
}

bool ParentDirectoryExists(const std::string& outputFilePath) {
  const std::filesystem::path parent =
      std::filesystem::path(outputFilePath).parent_path();
  if (parent.empty()) {
    return true;
  }
  std::error_code ec;
  return std::filesystem::exists(parent, ec) && !ec;
}
}  // namespace

RunAction::RunAction(const Config* config) : fConfig(config) {}

void RunAction::BeginOfRunAction(const G4Run* /*run*/) {
  // Validate once on master before worker tasks are launched.
  if (!IsMaster() || fConfig == nullptr) {
    return;
  }

  const Config::OutputFormat mode = fConfig->GetOutputFormat();
  std::string missingTargets;

  if (WritesCsv(mode)) {
    const std::string csvPath = fConfig->GetCsvFilePath();
    if (!ParentDirectoryExists(csvPath)) {
      missingTargets += "  - CSV target: " + csvPath + "\n";
    }
  }

  if (WritesHdf5(mode)) {
    const std::string hdf5Path = fConfig->GetHdf5FilePath();
    if (!ParentDirectoryExists(hdf5Path)) {
      missingTargets += "  - HDF5 target: " + hdf5Path + "\n";
    }
  }

  if (missingTargets.empty()) {
    return;
  }

  G4ExceptionDescription message;
  message
      << "Output directory validation failed before run start.\n"
      << "Expected output parent directories do not exist:\n"
      << missingTargets
      << "Create directories in Python before launching Geant4 "
      << "(for example via ConfigIO.ensure_output_directories / write_macro).";

  G4Exception("RunAction::BeginOfRunAction", "g4emi/output/missing-directory",
              FatalException, message);
}
