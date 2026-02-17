#ifndef SimIO_h
#define SimIO_h 1

#include "structures.hh"

#include <string>
#include <vector>

namespace SimIO {

/// Semantic row aliases shared between simulation logic and IO.
using PrimaryInfo = SimStructures::PrimaryInfo;
using SecondaryInfo = SimStructures::SecondaryInfo;
using PhotonInfo = SimStructures::PhotonInfo;
using CsvPhotonHitInfo = SimStructures::CsvPhotonHitInfo;

namespace detail {

/// Fixed width for species labels in HDF5 native row structures.
constexpr std::size_t kSpeciesLabelSize = SimStructures::detail::kHdf5SpeciesLabelSize;
/// Native in-memory row type used for `/primaries` HDF5 dataset writes.
using Hdf5PrimaryNativeRow = SimStructures::detail::Hdf5PrimaryNativeRow;
/// Native in-memory row type used for `/secondaries` HDF5 dataset writes.
using Hdf5SecondaryNativeRow = SimStructures::detail::Hdf5SecondaryNativeRow;
/// Native in-memory row type used for `/photons` HDF5 dataset writes.
using Hdf5PhotonNativeRow = SimStructures::detail::Hdf5PhotonNativeRow;
/// Internal HDF5-handle cache/state.
using Hdf5State = SimStructures::detail::Hdf5State;

}  // namespace detail

/**
 * Normalize a user-provided run-name into a single directory-safe token.
 *
 * Transformations:
 * - Trim leading/trailing whitespace.
 * - Remove one layer of matching single or double quotes.
 * - Replace path separators and embedded whitespace with underscores.
 */
std::string NormalizeRunName(const std::string& value);

/**
 * Strip a known output extension from a base file name/path.
 *
 * Recognized extensions are `.csv`, `.h5`, and `.hdf5` (case-insensitive).
 * Unknown extensions are preserved as-is.
 */
std::string StripKnownOutputExtension(const std::string& value);

/**
 * Compose an absolute output file path from base name, optional output-path
 * override, optional run-name, and file extension.
 *
 * Behavior summary:
 * - If `outputPath` is empty:
 *   - `runName` empty    -> preserve legacy base-path behavior.
 *   - `runName` nonempty -> route into repository `data/<runName>/`.
 * - If `outputPath` is set:
 *   - `runName` empty    -> write to `<outputPath>/<baseLeaf><extension>`.
 *   - `runName` nonempty -> write to `<outputPath>/<runName>/<baseLeaf><extension>`.
 *
 * Relative paths are anchored to the repository root.
 */
std::string ComposeOutputPath(const std::string& base,
                              const std::string& outputPath,
                              const std::string& runName,
                              const char* extension);

/// Append flat photon-hit rows to CSV output (creates header for new file).
bool AppendCsv(const std::string& csvPath,
               const std::vector<CsvPhotonHitInfo>& rows,
               std::string* errorMessage);

/// Append primary/secondary/photon rows to structured HDF5 datasets.
bool AppendHdf5(const std::string& hdf5Path,
                const std::vector<PrimaryInfo>& primaryRows,
                const std::vector<SecondaryInfo>& secondaryRows,
                const std::vector<PhotonInfo>& photonRows,
                std::string* errorMessage);

}  // namespace SimIO

#endif
