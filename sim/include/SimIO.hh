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

/// Normalize run name for filesystem-safe directory usage.
std::string NormalizeRunName(const std::string& value);

/// Strip `.h5` or `.hdf5` suffixes (case-insensitive) when present.
std::string StripKnownOutputExtension(const std::string& value);

/// Compose absolute output file path with run/output-path routing rules.
std::string ComposeOutputPath(const std::string& base,
                              const std::string& outputPath,
                              const std::string& runName,
                              const char* extension);

/// Append primary/secondary/photon rows to HDF5 datasets.
bool AppendHdf5(const std::string& hdf5Path,
                const std::vector<PrimaryInfo>& primaryRows,
                const std::vector<SecondaryInfo>& secondaryRows,
                const std::vector<PhotonInfo>& photonRows,
                std::string* errorMessage);

}  // namespace SimIO

#endif
