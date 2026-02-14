#ifndef utils_h
#define utils_h 1

#include <string>

/**
 * Shared string-normalization helpers used across simulation modules.
 *
 * Why this module exists:
 * - Keep common parsing and normalization behavior consistent between Config,
 *   SimIO, and messenger-driven command handling.
 * - Avoid duplicating subtle character-handling code (especially around
 *   std::tolower/std::isspace signed-char pitfalls).
 */
namespace Utils {

/**
 * Convert an arbitrary string to lowercase using C locale semantics.
 *
 * Usage:
 * - Case-insensitive command parsing (for example output format tokens).
 * - Normalizing filename extensions before comparison.
 *
 * Safety note:
 * - Each byte is cast to unsigned char before std::tolower to avoid undefined
 *   behavior when char is signed and contains values above 127.
 */
std::string ToLower(std::string value);

/**
 * Remove leading and trailing whitespace from a copy of the input string.
 *
 * Behavior:
 * - Strips only prefix/suffix whitespace recognized by std::isspace.
 * - Preserves all internal whitespace.
 * - Returns an empty string if input is all whitespace.
 *
 * The input is taken by value so callers can pass temporaries efficiently and
 * so normalization can be done in-place on the local copy.
 */
std::string Trim(std::string value);

/**
 * Remove one matching outer quote layer from a string.
 *
 * Behavior:
 * - If the input starts and ends with matching single quotes (') or matching
 *   double quotes ("), remove that one outer pair.
 * - If quotes are unmatched or string length is < 2, return unchanged.
 * - Nested quotes are intentionally not recursively stripped.
 */
std::string Unquote(const std::string& value);

}  // namespace Utils

#endif
