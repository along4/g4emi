#include "SimIO.hh"
#include "utils.hh"

#include <cctype>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <string>
#include <vector>

namespace SimIO {
namespace {
using Hdf5State = SimStructures::detail::Hdf5State;
using Hdf5PrimaryNativeRow = SimStructures::detail::Hdf5PrimaryNativeRow;
using Hdf5SecondaryNativeRow = SimStructures::detail::Hdf5SecondaryNativeRow;
using Hdf5PhotonNativeRow = SimStructures::detail::Hdf5PhotonNativeRow;
constexpr std::size_t kSpeciesLabelSize = SimStructures::detail::kHdf5SpeciesLabelSize;

/// Stage subdirectory for raw simulation output.
constexpr const char* kSimulatedPhotonsDir = "simulatedPhotons";

Hdf5State& GetState() {
  static Hdf5State state;
  return state;
}

// Close all open HDF5 handles in the cached writer state.
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

void CopyLabel(const std::string& in, char out[kSpeciesLabelSize]) {
  std::memset(out, 0, kSpeciesLabelSize);
  std::strncpy(out, in.c_str(), kSpeciesLabelSize - 1);
}

// Validate that an output file path has an existing parent directory.
bool EnsureParentDirectory(const std::string& filePath) {
  const std::filesystem::path path(filePath);
  const std::filesystem::path parent = path.parent_path();
  if (parent.empty()) {
    return true;
  }

  std::error_code ec;
  return std::filesystem::exists(parent, ec) && !ec;
}

hid_t CreateFixedStringType(std::size_t size) {
  const hid_t t = H5Tcopy(H5T_C_S1);
  H5Tset_size(t, size);
  H5Tset_strpad(t, H5T_STR_NULLTERM);
  return t;
}

// Open an existing 1D extendable dataset or create it if missing.
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

// Ensure cached HDF5 handles are initialized for the target output file.
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
      *errorMessage = "Output directory does not exist for " + hdf5Path;
    }
    return false;
  }

  std::error_code existsEc;
  if (std::filesystem::exists(hdf5Path, existsEc) && !existsEc) {
    s.file = H5Fopen(hdf5Path.c_str(), H5F_ACC_RDWR, H5P_DEFAULT);
  } else {
    s.file = H5Fcreate(hdf5Path.c_str(), H5F_ACC_TRUNC, H5P_DEFAULT, H5P_DEFAULT);
  }
  if (s.file < 0) {
    if (errorMessage) {
      *errorMessage = "Failed to open/create " + hdf5Path;
    }
    return false;
  }

  s.openPath = hdf5Path;

  const hid_t speciesType = CreateFixedStringType(kSpeciesLabelSize);

  s.primaryType = H5Tcreate(H5T_COMPOUND, sizeof(Hdf5PrimaryNativeRow));
  H5Tinsert(s.primaryType, "gun_call_id",
            HOFFSET(Hdf5PrimaryNativeRow, gun_call_id),
            H5T_NATIVE_INT64);
  H5Tinsert(s.primaryType, "primary_track_id",
            HOFFSET(Hdf5PrimaryNativeRow, primary_track_id), H5T_NATIVE_INT32);
  H5Tinsert(s.primaryType, "primary_species",
            HOFFSET(Hdf5PrimaryNativeRow, primary_species), speciesType);
  H5Tinsert(s.primaryType, "primary_x_mm",
            HOFFSET(Hdf5PrimaryNativeRow, primary_x_mm),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.primaryType, "primary_y_mm",
            HOFFSET(Hdf5PrimaryNativeRow, primary_y_mm),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.primaryType, "primary_energy_MeV",
            HOFFSET(Hdf5PrimaryNativeRow, primary_energy_MeV),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.primaryType, "primary_interaction_time_ns",
            HOFFSET(Hdf5PrimaryNativeRow, primary_interaction_time_ns),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.primaryType, "primary_created_secondary_count",
            HOFFSET(Hdf5PrimaryNativeRow, primary_created_secondary_count),
            H5T_NATIVE_INT64);
  H5Tinsert(s.primaryType, "primary_generated_optical_photon_count",
            HOFFSET(Hdf5PrimaryNativeRow, primary_generated_optical_photon_count),
            H5T_NATIVE_INT64);
  H5Tinsert(s.primaryType, "primary_detected_optical_interface_photon_count",
            HOFFSET(Hdf5PrimaryNativeRow,
                    primary_detected_optical_interface_photon_count),
            H5T_NATIVE_INT64);

  s.secondaryType = H5Tcreate(H5T_COMPOUND, sizeof(Hdf5SecondaryNativeRow));
  H5Tinsert(s.secondaryType, "gun_call_id",
            HOFFSET(Hdf5SecondaryNativeRow, gun_call_id), H5T_NATIVE_INT64);
  H5Tinsert(s.secondaryType, "primary_track_id",
            HOFFSET(Hdf5SecondaryNativeRow, primary_track_id), H5T_NATIVE_INT32);
  H5Tinsert(s.secondaryType, "secondary_track_id",
            HOFFSET(Hdf5SecondaryNativeRow, secondary_track_id),
            H5T_NATIVE_INT32);
  H5Tinsert(s.secondaryType, "secondary_species",
            HOFFSET(Hdf5SecondaryNativeRow, secondary_species), speciesType);
  H5Tinsert(s.secondaryType, "secondary_origin_x_mm",
            HOFFSET(Hdf5SecondaryNativeRow, secondary_origin_x_mm),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.secondaryType, "secondary_origin_y_mm",
            HOFFSET(Hdf5SecondaryNativeRow, secondary_origin_y_mm),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.secondaryType, "secondary_origin_z_mm",
            HOFFSET(Hdf5SecondaryNativeRow, secondary_origin_z_mm),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.secondaryType, "secondary_origin_energy_MeV",
            HOFFSET(Hdf5SecondaryNativeRow, secondary_origin_energy_MeV),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.secondaryType, "secondary_end_x_mm",
            HOFFSET(Hdf5SecondaryNativeRow, secondary_end_x_mm),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.secondaryType, "secondary_end_y_mm",
            HOFFSET(Hdf5SecondaryNativeRow, secondary_end_y_mm),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.secondaryType, "secondary_end_z_mm",
            HOFFSET(Hdf5SecondaryNativeRow, secondary_end_z_mm),
            H5T_NATIVE_DOUBLE);

  s.photonType = H5Tcreate(H5T_COMPOUND, sizeof(Hdf5PhotonNativeRow));
  H5Tinsert(s.photonType, "gun_call_id",
            HOFFSET(Hdf5PhotonNativeRow, gun_call_id),
            H5T_NATIVE_INT64);
  H5Tinsert(s.photonType, "primary_track_id",
            HOFFSET(Hdf5PhotonNativeRow, primary_track_id), H5T_NATIVE_INT32);
  H5Tinsert(s.photonType, "secondary_track_id",
            HOFFSET(Hdf5PhotonNativeRow, secondary_track_id),
            H5T_NATIVE_INT32);
  H5Tinsert(s.photonType, "photon_track_id",
            HOFFSET(Hdf5PhotonNativeRow, photon_track_id), H5T_NATIVE_INT32);
  H5Tinsert(s.photonType, "photon_creation_time_ns",
            HOFFSET(Hdf5PhotonNativeRow, photon_creation_time_ns),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.photonType, "photon_origin_x_mm",
            HOFFSET(Hdf5PhotonNativeRow, photon_origin_x_mm),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.photonType, "photon_origin_y_mm",
            HOFFSET(Hdf5PhotonNativeRow, photon_origin_y_mm),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.photonType, "photon_origin_z_mm",
            HOFFSET(Hdf5PhotonNativeRow, photon_origin_z_mm),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.photonType, "photon_scint_exit_x_mm",
            HOFFSET(Hdf5PhotonNativeRow, photon_scint_exit_x_mm),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.photonType, "photon_scint_exit_y_mm",
            HOFFSET(Hdf5PhotonNativeRow, photon_scint_exit_y_mm),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.photonType, "photon_scint_exit_z_mm",
            HOFFSET(Hdf5PhotonNativeRow, photon_scint_exit_z_mm),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.photonType, "optical_interface_hit_x_mm",
            HOFFSET(Hdf5PhotonNativeRow, optical_interface_hit_x_mm),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.photonType, "optical_interface_hit_y_mm",
            HOFFSET(Hdf5PhotonNativeRow, optical_interface_hit_y_mm),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.photonType, "optical_interface_hit_time_ns",
            HOFFSET(Hdf5PhotonNativeRow, optical_interface_hit_time_ns),
            H5T_NATIVE_DOUBLE);

  // Optical-interface state at crossing for downstream transport.
  H5Tinsert(s.photonType, "optical_interface_hit_dir_x",
            HOFFSET(Hdf5PhotonNativeRow, optical_interface_hit_dir_x),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.photonType, "optical_interface_hit_dir_y",
            HOFFSET(Hdf5PhotonNativeRow, optical_interface_hit_dir_y),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.photonType, "optical_interface_hit_dir_z",
            HOFFSET(Hdf5PhotonNativeRow, optical_interface_hit_dir_z),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.photonType, "optical_interface_hit_pol_x",
            HOFFSET(Hdf5PhotonNativeRow, optical_interface_hit_pol_x),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.photonType, "optical_interface_hit_pol_y",
            HOFFSET(Hdf5PhotonNativeRow, optical_interface_hit_pol_y),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.photonType, "optical_interface_hit_pol_z",
            HOFFSET(Hdf5PhotonNativeRow, optical_interface_hit_pol_z),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.photonType, "optical_interface_hit_energy_eV",
            HOFFSET(Hdf5PhotonNativeRow, optical_interface_hit_energy_eV),
            H5T_NATIVE_DOUBLE);
  H5Tinsert(s.photonType, "optical_interface_hit_wavelength_nm",
            HOFFSET(Hdf5PhotonNativeRow, optical_interface_hit_wavelength_nm),
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

std::vector<Hdf5PrimaryNativeRow> ToNative(const std::vector<PrimaryInfo>& rows) {
  std::vector<Hdf5PrimaryNativeRow> out;
  out.reserve(rows.size());
  for (const auto& row : rows) {
    Hdf5PrimaryNativeRow native{};
    native.gun_call_id = row.gunCallId;
    native.primary_track_id = row.primaryTrackId;
    CopyLabel(row.primarySpecies, native.primary_species);
    native.primary_x_mm = row.primaryXmm;
    native.primary_y_mm = row.primaryYmm;
    native.primary_energy_MeV = row.primaryEnergyMeV;
    native.primary_interaction_time_ns = row.primaryInteractionTimeNs;
    native.primary_created_secondary_count = row.primaryCreatedSecondaryCount;
    native.primary_generated_optical_photon_count =
        row.primaryGeneratedOpticalPhotonCount;
    native.primary_detected_optical_interface_photon_count =
        row.primaryDetectedOpticalInterfacePhotonCount;
    out.push_back(native);
  }
  return out;
}

std::vector<Hdf5SecondaryNativeRow> ToNative(const std::vector<SecondaryInfo>& rows) {
  std::vector<Hdf5SecondaryNativeRow> out;
  out.reserve(rows.size());
  for (const auto& row : rows) {
    Hdf5SecondaryNativeRow native{};
    native.gun_call_id = row.gunCallId;
    native.primary_track_id = row.primaryTrackId;
    native.secondary_track_id = row.secondaryTrackId;
    CopyLabel(row.secondarySpecies, native.secondary_species);
    native.secondary_origin_x_mm = row.secondaryOriginXmm;
    native.secondary_origin_y_mm = row.secondaryOriginYmm;
    native.secondary_origin_z_mm = row.secondaryOriginZmm;
    native.secondary_origin_energy_MeV = row.secondaryOriginEnergyMeV;
    native.secondary_end_x_mm = row.secondaryEndXmm;
    native.secondary_end_y_mm = row.secondaryEndYmm;
    native.secondary_end_z_mm = row.secondaryEndZmm;
    out.push_back(native);
  }
  return out;
}

std::vector<Hdf5PhotonNativeRow> ToNative(const std::vector<PhotonInfo>& rows) {
  std::vector<Hdf5PhotonNativeRow> out;
  out.reserve(rows.size());
  for (const auto& row : rows) {
    Hdf5PhotonNativeRow native{};
    native.gun_call_id = row.gunCallId;
    native.primary_track_id = row.primaryTrackId;
    native.secondary_track_id = row.secondaryTrackId;
    native.photon_track_id = row.photonTrackId;
    native.photon_creation_time_ns = row.photonCreationTimeNs;
    native.photon_origin_x_mm = row.photonOriginXmm;
    native.photon_origin_y_mm = row.photonOriginYmm;
    native.photon_origin_z_mm = row.photonOriginZmm;
    native.photon_scint_exit_x_mm = row.photonScintExitXmm;
    native.photon_scint_exit_y_mm = row.photonScintExitYmm;
    native.photon_scint_exit_z_mm = row.photonScintExitZmm;
    native.optical_interface_hit_x_mm = row.opticalInterfaceHitXmm;
    native.optical_interface_hit_y_mm = row.opticalInterfaceHitYmm;
    native.optical_interface_hit_time_ns = row.opticalInterfaceHitTimeNs;
    native.optical_interface_hit_dir_x = row.opticalInterfaceHitDirX;
    native.optical_interface_hit_dir_y = row.opticalInterfaceHitDirY;
    native.optical_interface_hit_dir_z = row.opticalInterfaceHitDirZ;
    native.optical_interface_hit_pol_x = row.opticalInterfaceHitPolX;
    native.optical_interface_hit_pol_y = row.opticalInterfaceHitPolY;
    native.optical_interface_hit_pol_z = row.opticalInterfaceHitPolZ;
    native.optical_interface_hit_energy_eV = row.opticalInterfaceHitEnergyEV;
    native.optical_interface_hit_wavelength_nm = row.opticalInterfaceHitWavelengthNm;
    out.push_back(native);
  }
  return out;
}
}  // namespace

// Normalize a run name into a directory-safe token.
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

// Strip `.h5`/`.hdf5` suffixes (case-insensitive) when present.
std::string StripKnownOutputExtension(const std::string& value) {
  const std::filesystem::path path(value);
  const std::string ext = Utils::ToLower(path.extension().string());

  if (ext != ".h5" && ext != ".hdf5") {
    return value;
  }

  const std::filesystem::path base = path.parent_path() / path.stem();
  return base.string();
}

// Resolve a relative path against repository root (or cwd fallback).
std::filesystem::path ResolveAgainstRepositoryRoot(std::filesystem::path path) {
  if (!path.is_relative()) {
    return path;
  }
#ifdef G4EMI_REPO_ROOT
  return std::filesystem::path(G4EMI_REPO_ROOT) / path;
#else
  return std::filesystem::current_path() / path;
#endif
}

// Ensure simulation outputs live under the `simulatedPhotons` stage directory.
std::filesystem::path AppendSimulatedPhotonsDir(std::filesystem::path root) {
  if (root.filename() == kSimulatedPhotonsDir) {
    return root;
  }
  return root / kSimulatedPhotonsDir;
}

// Compose absolute output path from base name, output path override, and run name.
std::string ComposeOutputPath(const std::string& base,
                              const std::string& outputPath,
                              const std::string& runName,
                              const char* extension) {
  const std::string safeBase =
      base.empty() ? "data/photon_optical_interface_hits" : base;

  std::filesystem::path basePath = ResolveAgainstRepositoryRoot(safeBase);
  const std::string baseLeaf = basePath.filename().string().empty()
                                   ? "photon_optical_interface_hits"
                                   : basePath.filename().string();

  if (!outputPath.empty()) {
    std::filesystem::path explicitDir = ResolveAgainstRepositoryRoot(outputPath);
    if (!runName.empty()) {
      explicitDir /= runName;
    }
    explicitDir = AppendSimulatedPhotonsDir(explicitDir);
    return (explicitDir / baseLeaf).string() + extension;
  }

  if (runName.empty()) {
    // No output override and no run name: use base parent + simulatedPhotons/.
    std::filesystem::path root = basePath.parent_path();
    if (root.empty()) {
#ifdef G4EMI_REPO_ROOT
      root = std::filesystem::path(G4EMI_REPO_ROOT) / "data";
#else
      root = std::filesystem::current_path() / "data";
#endif
    }
    root = AppendSimulatedPhotonsDir(root);
    return (root / baseLeaf).string() + extension;
  }

  // With run name and no output override, route through data/<runName>/simulatedPhotons.
#ifdef G4EMI_REPO_ROOT
  std::filesystem::path runDir =
      std::filesystem::path(G4EMI_REPO_ROOT) / "data" / runName;
#else
  std::filesystem::path runDir =
      std::filesystem::current_path() / "data" / runName;
#endif
  runDir = AppendSimulatedPhotonsDir(runDir);

  return (runDir / baseLeaf).string() + extension;
}

// Append semantic row containers into /primaries, /secondaries, and /photons.
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
