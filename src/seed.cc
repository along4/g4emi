#include "seed.hh"

#include "G4Types.hh"
#include "G4ios.hh"
#include "Randomize.hh"

#include <chrono>
#include <cstdint>
#include <random>

namespace {
/**
 * SplitMix64 mixer used to decorrelate entropy bits before converting to Geant4
 * seeds.
 */
std::uint64_t Mix64(std::uint64_t x) {
  x += 0x9e3779b97f4a7c15ULL;
  x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
  x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
  return x ^ (x >> 31);
}

/**
 * Convert raw entropy into a positive Geant4-compatible seed value.
 */
G4long ToSeed(std::uint64_t value) {
  const std::uint64_t mixed = Mix64(value);
  const std::uint64_t positive = mixed & 0x7fffffffffffffffULL;
  return (positive == 0ULL) ? 1 : static_cast<G4long>(positive);
}
}  // namespace

namespace Seed {

/**
 * Generate fresh master seeds for each process invocation.
 *
 * The user can still override this in macro files with `/random/setSeeds`.
 */
void SetAutoMasterSeeds() {
  const auto now = std::chrono::high_resolution_clock::now().time_since_epoch();
  const auto nowNs = static_cast<std::uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(now).count());

  std::random_device rd;
  const std::uint64_t entropyA = (static_cast<std::uint64_t>(rd()) << 32) ^ rd();
  const std::uint64_t entropyB = (static_cast<std::uint64_t>(rd()) << 32) ^ rd();

  G4long seeds[2] = {
      ToSeed(nowNs ^ entropyA ^ 0xa5a5a5a5ULL),
      ToSeed((nowNs << 1) ^ entropyB ^ 0x5a5a5a5aULL),
  };

  if (seeds[0] == seeds[1]) {
    seeds[1] = ToSeed(static_cast<std::uint64_t>(seeds[0]) ^ 0x9e3779b9ULL);
  }

  G4Random::setTheSeeds(seeds, 2);
  G4cout << "Auto RNG master seeds: (" << seeds[0] << ", " << seeds[1]
         << "). Use /random/setSeeds to override." << G4endl;
}

}  // namespace Seed
