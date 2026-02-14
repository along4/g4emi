#include "SimIO.hh"
#include "utils.hh"

#include <cctype>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

/**
 * SimIO centralizes all persistent output writing for the simulation.
 *
 * Design intent:
 * - Event/stepping/tracking code produces semantic row containers.
 * - This module owns all file-format concerns (CSV schema text and HDF5 layout).
 * - HDF5 resources are cached process-wide to avoid re-opening datasets on every
 *   event write.
 *
 * Threading note:
 * - Callers are responsible for external synchronization when multiple threads
 *   may append concurrently (EventAction uses a global mutex).
 */
namespace SimIO {
namespace {
/**
 * Access the process-global HDF5 writer state singleton.
 *
 * This state stores live HDF5 handles and the currently open path so append
 * operations can reuse open resources across events.
 */
detail::Hdf5State& GetState() {
  static detail::Hdf5State state;
  return state;
}

/**
 * Close all open HDF5 handles currently tracked by the global writer state.
 *
 * This function is idempotent: it checks each handle before closing and resets
 * handle fields to invalid sentinel values afterwards.
 */
void CloseAll() {
  auto& s = GetState();
  if (s.primariesDs >= 0) {
    H5Dclose(s.primariesDs);
    s.primariesDs = -1;
  }
  if (s.secondariesDs >= 0) {
    H5Dclose(s.secondariesDs);
    s.secondariesDs = -1;
  }
  if (s.photonsDs >= 0) {
    H5Dclose(s.photonsDs);
    s.photonsDs = -1;
  }
  if (s.primaryType >= 0) {
    H5Tclose(s.primaryType);
    s.primaryType = -1;
  }
  if (s.secondaryType >= 0) {
    H5Tclose(s.secondaryType);
    s.secondaryType = -1;
  }
  if (s.photonType >= 0) {
    H5Tclose(s.photonType);
    s.photonType = -1;
  }
  if (s.file >= 0) {
    H5Fclose(s.file);
    s.file = -1;
  }
  s.openPath.clear();
}

/**
 * Copy a species label from std::string into a fixed-size null-terminated
 * character buffer used by HDF5 compound rows.
 */
void CopyLabel(const std::string& in, char out[detail::kSpeciesLabelSize]) {
  std::memset(out, 0, detail::kSpeciesLabelSize);
  std::strncpy(out, in.c_str(), detail::kSpeciesLabelSize - 1);
}

/**
 * Ensure parent directory exists for an output file path.
 *
 * Returns true when:
 * - file has no parent directory (current directory target), or
 * - parent directory already exists, or
 * - directory creation succeeded.
 */
bool EnsureParentDirectory(const std::string& filePath) {
  const std::filesystem::path path(filePath);
  const std::filesystem::path parent = path.parent_path();
  if (parent.empty()) {
    return true;
  }

  std::error_code ec;
  if (std::filesystem::exists(parent, ec)) {
    return !ec;
  }

  std::filesystem::create_directories(parent, ec);
  if (ec) {
    return false;
  }

  return std::filesystem::exists(parent);
}

/**
 * Create an HDF5 fixed-length C-string type with explicit null termination.
 *
 * Caller owns the returned type handle and must close it with H5Tclose.
 */
hid_t CreateFixedStringType(std::size_t size) {
  const hid_t t = H5Tcopy(H5T_C_S1);
  H5Tset_size(t, size);
  H5Tset_strpad(t, H5T_STR_NULLTERM);
  return t;
}

/**
 * Open an existing 1D extendable dataset or create it if missing.
 *
 * Dataset properties:
 * - rank: 1
 * - initial size: 0 rows
 * - max size: unlimited
 * - chunk size: 4096 rows for append efficiency
 */
hid_t CreateExtendableDataset(hid_t file, const char* name, hid_t rowType) {
  if (H5Lexists(file, name, H5P_DEFAULT) > 0) {
    return H5Dopen2(file, name, H5P_DEFAULT);
  }

  hsize_t dims[1] = {0};
  hsize_t maxDims[1] = {H5S_UNLIMITED};
  const hid_t space = H5Screate_simple(1, dims, maxDims);
  const hid_t dcpl = H5Pcreate(H5P_DATASET_CREATE);
  hsize_t chunkDims[1] = {4096};
  H5Pset_chunk(dcpl, 1, chunkDims);

  const hid_t ds = H5Dcreate2(file, name, rowType, space, H5P_DEFAULT, dcpl,
                              H5P_DEFAULT);

  H5Pclose(dcpl);
  H5Sclose(space);
  return ds;
}

/**
 * Append native POD rows into an extendable HDF5 dataset.
 *
 * Workflow:
 * 1. Query current dataset extent.
 * 2. Extend extent by nRows.
 * 3. Select a hyperslab at the appended region.
 * 4. Write caller-provided contiguous row block.
 */
bool AppendNativeRows(hid_t dataset,
                      hid_t rowType,
                      const void* data,
                      hsize_t nRows) {
  if (dataset < 0 || rowType < 0 || !data || nRows == 0) {
    return true;
  }

  const hid_t oldSpace = H5Dget_space(dataset);
  hsize_t oldDims[1] = {0};
  H5Sget_simple_extent_dims(oldSpace, oldDims, nullptr);
  H5Sclose(oldSpace);

  hsize_t newDims[1] = {oldDims[0] + nRows};
  if (H5Dset_extent(dataset, newDims) < 0) {
    return false;
  }

  const hid_t fileSpace = H5Dget_space(dataset);
  hsize_t start[1] = {oldDims[0]};
  hsize_t count[1] = {nRows};
  H5Sselect_hyperslab(fileSpace, H5S_SELECT_SET, start, nullptr, count, nullptr);

  const hid_t memSpace = H5Screate_simple(1, count, nullptr);
  const herr_t writeStatus =
      H5Dwrite(dataset, rowType, memSpace, fileSpace, H5P_DEFAULT, data);

  H5Sclose(memSpace);
  H5Sclose(fileSpace);
  return writeStatus >= 0;
}

/**
 * Ensure the HDF5 writer is initialized for the requested file path.
 *
 * Behavior:
 * - Reuses existing open handles when the same path is requested.
 * - Closes and reopens all handles when path changes.
 * - Opens existing file in read/write mode, otherwise creates a new file.
 * - Ensures required datasets and compound row types are ready.
 */
bool EnsureReady(const std::string& hdf5Path, std::string* errorMessage) {
  auto& s = GetState();
  if (s.file >= 0 && s.openPath == hdf5Path) {
    return true;
  }

  if (s.file >= 0 && s.openPath != hdf5Path) {
    CloseAll();
  }

  if (!EnsureParentDirectory(hdf5Path)) {
    if (errorMessage) {
      *errorMessage = "Failed to create output directory for " + hdf5Path;
    }
    return false;
  }

  {
    std::ifstream in(hdf5Path);
    if (in.good()) {
      s.file = H5Fopen(hdf5Path.c_str(), H5F_ACC_RDWR, H5P_DEFAULT);
    } else {
      s.file =
          H5Fcreate(hdf5Path.c_str(), H5F_ACC_TRUNC, H5P_DEFAULT, H5P_DEFAULT);
    }
  }
  if (s.file < 0) {
    if (errorMessage) {
      *errorMessage = "Failed to open/create " + hdf5Path;
    }
    return false;
  }

  s.openPath = hdf5Path;

  const hid_t speciesType = CreateFixedStringType(detail::kSpeciesLabelSize);

  s.primaryType = H5Tcreate(H5T_COMPOUND, sizeof(detail::Hdf5PrimaryNativeRow));
  H5Tinsert(s.primaryType, "gun_call_id",
            HOFFSET(detail::Hdf5PrimaryNativeRow, gun_call_id),
            H5T_NATIVE_INT64);
  H5Tinsert(s.primaryType, "primary_track_id",
            HOFFSET(detail::Hdf5PrimaryNativeRow, primary_track_id), H5T_NATIVE_INT32);
  H5Tinsert(s.primaryType, "primary_species",
            HOFFSET(detail::Hdf5PrimaryNativeRow, primary_species), speciesType);
  H5Tinsert(s.primaryType, "primary_x_mm",
            HOFFSET(detail::Hdf5PrimaryNativeRow, primary_x_mm),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.primaryType, "primary_y_mm",
            HOFFSET(detail::Hdf5PrimaryNativeRow, primary_y_mm),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.primaryType, "primary_energy_MeV",
            HOFFSET(detail::Hdf5PrimaryNativeRow, primary_energy_MeV),
            H5T_NATIVE_DOUBLE);

  s.secondaryType = H5Tcreate(H5T_COMPOUND, sizeof(detail::Hdf5SecondaryNativeRow));
  H5Tinsert(s.secondaryType, "gun_call_id",
            HOFFSET(detail::Hdf5SecondaryNativeRow, gun_call_id), H5T_NATIVE_INT64);
  H5Tinsert(s.secondaryType, "primary_track_id",
            HOFFSET(detail::Hdf5SecondaryNativeRow, primary_track_id),
            H5T_NATIVE_INT32);
  H5Tinsert(s.secondaryType, "secondary_track_id",
            HOFFSET(detail::Hdf5SecondaryNativeRow, secondary_track_id),
            H5T_NATIVE_INT32);
  H5Tinsert(s.secondaryType, "secondary_species",
            HOFFSET(detail::Hdf5SecondaryNativeRow, secondary_species), speciesType);
  H5Tinsert(s.secondaryType, "secondary_origin_x_mm",
            HOFFSET(detail::Hdf5SecondaryNativeRow, secondary_origin_x_mm),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.secondaryType, "secondary_origin_y_mm",
            HOFFSET(detail::Hdf5SecondaryNativeRow, secondary_origin_y_mm),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.secondaryType, "secondary_origin_z_mm",
            HOFFSET(detail::Hdf5SecondaryNativeRow, secondary_origin_z_mm),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.secondaryType, "secondary_origin_energy_MeV",
            HOFFSET(detail::Hdf5SecondaryNativeRow, secondary_origin_energy_MeV),
            H5T_NATIVE_DOUBLE);

  s.photonType = H5Tcreate(H5T_COMPOUND, sizeof(detail::Hdf5PhotonNativeRow));
  H5Tinsert(s.photonType, "gun_call_id",
            HOFFSET(detail::Hdf5PhotonNativeRow, gun_call_id),
            H5T_NATIVE_INT64);
  H5Tinsert(s.photonType, "primary_track_id",
            HOFFSET(detail::Hdf5PhotonNativeRow, primary_track_id), H5T_NATIVE_INT32);
  H5Tinsert(s.photonType, "secondary_track_id",
            HOFFSET(detail::Hdf5PhotonNativeRow, secondary_track_id),
            H5T_NATIVE_INT32);
  H5Tinsert(s.photonType, "photon_track_id",
            HOFFSET(detail::Hdf5PhotonNativeRow, photon_track_id), H5T_NATIVE_INT32);
  H5Tinsert(s.photonType, "photon_origin_x_mm",
            HOFFSET(detail::Hdf5PhotonNativeRow, photon_origin_x_mm),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.photonType, "photon_origin_y_mm",
            HOFFSET(detail::Hdf5PhotonNativeRow, photon_origin_y_mm),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.photonType, "photon_origin_z_mm",
            HOFFSET(detail::Hdf5PhotonNativeRow, photon_origin_z_mm),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.photonType, "sensor_hit_x_mm",
            HOFFSET(detail::Hdf5PhotonNativeRow, sensor_hit_x_mm),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.photonType, "sensor_hit_y_mm",
            HOFFSET(detail::Hdf5PhotonNativeRow, sensor_hit_y_mm),
            H5T_NATIVE_DOUBLE);

  H5Tclose(speciesType);

  s.primariesDs = CreateExtendableDataset(s.file, "/primaries", s.primaryType);
  s.secondariesDs = CreateExtendableDataset(s.file, "/secondaries", s.secondaryType);
  s.photonsDs = CreateExtendableDataset(s.file, "/photons", s.photonType);

  if (s.primariesDs < 0 || s.secondariesDs < 0 || s.photonsDs < 0) {
    if (errorMessage) {
      *errorMessage = "Failed to initialize datasets in " + hdf5Path;
    }
    return false;
  }

  if (!s.registeredAtExit) {
    std::atexit(CloseAll);
    s.registeredAtExit = true;
  }

  return true;
}

/**
 * Convert semantic primary row containers into HDF5-native POD rows.
 */
std::vector<detail::Hdf5PrimaryNativeRow> ToNative(
    const std::vector<PrimaryInfo>& rows) {
  std::vector<detail::Hdf5PrimaryNativeRow> out;
  out.reserve(rows.size());
  for (const auto& row : rows) {
    detail::Hdf5PrimaryNativeRow native{};
    native.gun_call_id = row.gunCallId;
    native.primary_track_id = row.primaryTrackId;
    CopyLabel(row.primarySpecies, native.primary_species);
    native.primary_x_mm = row.primaryXmm;
    native.primary_y_mm = row.primaryYmm;
    native.primary_energy_MeV = row.primaryEnergyMeV;
    out.push_back(native);
  }
  return out;
}

/**
 * Convert semantic secondary row containers into HDF5-native POD rows.
 */
std::vector<detail::Hdf5SecondaryNativeRow> ToNative(
    const std::vector<SecondaryInfo>& rows) {
  std::vector<detail::Hdf5SecondaryNativeRow> out;
  out.reserve(rows.size());
  for (const auto& row : rows) {
    detail::Hdf5SecondaryNativeRow native{};
    native.gun_call_id = row.gunCallId;
    native.primary_track_id = row.primaryTrackId;
    native.secondary_track_id = row.secondaryTrackId;
    CopyLabel(row.secondarySpecies, native.secondary_species);
    native.secondary_origin_x_mm = row.secondaryOriginXmm;
    native.secondary_origin_y_mm = row.secondaryOriginYmm;
    native.secondary_origin_z_mm = row.secondaryOriginZmm;
    native.secondary_origin_energy_MeV = row.secondaryOriginEnergyMeV;
    out.push_back(native);
  }
  return out;
}

/**
 * Convert semantic photon row containers into HDF5-native POD rows.
 */
std::vector<detail::Hdf5PhotonNativeRow> ToNative(
    const std::vector<PhotonInfo>& rows) {
  std::vector<detail::Hdf5PhotonNativeRow> out;
  out.reserve(rows.size());
  for (const auto& row : rows) {
    detail::Hdf5PhotonNativeRow native{};
    native.gun_call_id = row.gunCallId;
    native.primary_track_id = row.primaryTrackId;
    native.secondary_track_id = row.secondaryTrackId;
    native.photon_track_id = row.photonTrackId;
    native.photon_origin_x_mm = row.photonOriginXmm;
    native.photon_origin_y_mm = row.photonOriginYmm;
    native.photon_origin_z_mm = row.photonOriginZmm;
    native.sensor_hit_x_mm = row.sensorHitXmm;
    native.sensor_hit_y_mm = row.sensorHitYmm;
    out.push_back(native);
  }
  return out;
}
}  // namespace

/**
 * Normalize a user-provided run-name into a single directory-safe token.
 *
 * Transformations:
 * - Trim leading/trailing whitespace.
 * - Remove one layer of matching single or double quotes.
 * - Replace path separators and embedded whitespace with underscores.
 */
std::string NormalizeRunName(const std::string& value) {
  std::string normalized = Utils::Unquote(Utils::Trim(value));

  for (char& c : normalized) {
    const unsigned char uc = static_cast<unsigned char>(c);
    if (c == '/' || c == '\\' || std::isspace(uc)) {
      c = '_';
    }
  }

  return normalized;
}

/**
 * Strip a known output extension from a base file name/path.
 *
 * Recognized extensions are `.csv`, `.h5`, and `.hdf5` (case-insensitive).
 */
std::string StripKnownOutputExtension(const std::string& value) {
  const std::filesystem::path path(value);
  const std::string ext = Utils::ToLower(path.extension().string());

  if (ext != ".csv" && ext != ".h5" && ext != ".hdf5") {
    return value;
  }

  const std::filesystem::path base = path.parent_path() / path.stem();
  return base.string();
}

/**
 * Compose an absolute output file path from base name, optional run name, and
 * output extension.
 */
std::string ComposeOutputPath(const std::string& base,
                              const std::string& runName,
                              const char* extension) {
  const std::string safeBase = base.empty() ? "data/photon_sensor_hits" : base;

  std::filesystem::path basePath(safeBase);
  if (basePath.is_relative()) {
#ifdef G4EMI_REPO_ROOT
    basePath = std::filesystem::path(G4EMI_REPO_ROOT) / basePath;
#else
    basePath = std::filesystem::current_path() / basePath;
#endif
  }

  if (runName.empty()) {
    return basePath.string() + extension;
  }

  std::string leaf = basePath.filename().string();
  if (leaf.empty()) {
    leaf = "photon_sensor_hits";
  }

#ifdef G4EMI_REPO_ROOT
  const std::filesystem::path runDir =
      std::filesystem::path(G4EMI_REPO_ROOT) / "data" / runName;
#else
  const std::filesystem::path runDir =
      std::filesystem::current_path() / "data" / runName;
#endif

  return (runDir / leaf).string() + extension;
}

/**
 * Append photon-hit rows to CSV output.
 *
 * The function writes the CSV header when the target file is new or empty,
 * then appends one line per row using the canonical project column ordering.
 */
bool AppendCsv(const std::string& csvPath,
               const std::vector<CsvPhotonHitInfo>& rows,
               std::string* errorMessage) {
  if (!EnsureParentDirectory(csvPath)) {
    if (errorMessage) {
      *errorMessage = "Failed to create output directory for " + csvPath;
    }
    return false;
  }

  bool writeHeader = false;
  {
    std::ifstream in(csvPath);
    writeHeader = !in.good() || (in.peek() == std::ifstream::traits_type::eof());
  }

  std::ofstream out(csvPath, std::ios::app);
  if (!out) {
    if (errorMessage) {
      *errorMessage = "Failed to open " + csvPath + " for writing.";
    }
    return false;
  }

  if (writeHeader) {
    out << "event_id,primary_id,secondary_id,photon_id,prim_spec,prim_x,prim_y,sec_spec,"
           "sec_origin_x,sec_origin_y,sec_origin_z,sec_origin_eng,scin_orig_x,"
           "scin_orig_y,scin_orig_z,scin_face_x,scin_face_y\n";
  }

  for (const auto& row : rows) {
    out << row.eventId << "," << row.primaryId << "," << row.secondaryId << ","
        << row.photonId << "," << row.primarySpecies << "," << row.primaryXmm << ","
        << row.primaryYmm << "," << row.secondarySpecies << ","
        << row.secondaryOriginXmm << "," << row.secondaryOriginYmm << ","
        << row.secondaryOriginZmm << "," << row.secondaryOriginEnergyMeV << ","
        << row.scintOriginXmm << "," << row.scintOriginYmm << ","
        << row.scintOriginZmm << "," << row.sensorHitXmm << ","
        << row.sensorHitYmm << "\n";
  }

  return true;
}

/**
 * Append semantic primary/secondary/photon containers into the HDF5 file.
 *
 * Dataset mapping:
 * - /primaries   <- primaryRows
 * - /secondaries <- secondaryRows
 * - /photons     <- photonRows
 */
bool AppendHdf5(const std::string& hdf5Path,
                const std::vector<PrimaryInfo>& primaryRows,
                const std::vector<SecondaryInfo>& secondaryRows,
                const std::vector<PhotonInfo>& photonRows,
                std::string* errorMessage) {
  if (!EnsureReady(hdf5Path, errorMessage)) {
    return false;
  }

  auto primaryNative = ToNative(primaryRows);
  auto secondaryNative = ToNative(secondaryRows);
  auto photonNative = ToNative(photonRows);

  auto& s = GetState();
  if (!primaryNative.empty() &&
      !AppendNativeRows(s.primariesDs, s.primaryType, primaryNative.data(),
                        static_cast<hsize_t>(primaryNative.size()))) {
    if (errorMessage) {
      *errorMessage = "Failed appending /primaries rows to " + hdf5Path;
    }
    return false;
  }

  if (!secondaryNative.empty() &&
      !AppendNativeRows(s.secondariesDs, s.secondaryType, secondaryNative.data(),
                        static_cast<hsize_t>(secondaryNative.size()))) {
    if (errorMessage) {
      *errorMessage = "Failed appending /secondaries rows to " + hdf5Path;
    }
    return false;
  }

  if (!photonNative.empty() &&
      !AppendNativeRows(s.photonsDs, s.photonType, photonNative.data(),
                        static_cast<hsize_t>(photonNative.size()))) {
    if (errorMessage) {
      *errorMessage = "Failed appending /photons rows to " + hdf5Path;
    }
    return false;
  }

  return true;
}

}  // namespace SimIO
