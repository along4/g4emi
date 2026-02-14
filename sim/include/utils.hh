#ifndef utils_h
#define utils_h 1

#include <string>

namespace Utils {

/**
 * Convert an arbitrary string to lowercase using C locale semantics.
 *
 * This helper is intended for case-insensitive command/format parsing.
 * Each character is cast to unsigned char before std::tolower to avoid
 * undefined behavior for non-ASCII byte values.
 */
std::string ToLower(std::string value);

/**
 * Remove leading and trailing whitespace from a copy of the input string.
 *
 * Internal spacing is preserved. The input is passed by value so callers can
 * move into this function without allocating another temporary.
 */
std::string Trim(std::string value);

/**
 * Remove one matching outer quote layer from a string.
 *
 * If the input starts/ends with matching single quotes (') or double quotes (")
 * and length is at least two characters, the outer pair is removed. Otherwise,
 * the input is returned unchanged.
 */
std::string Unquote(const std::string& value);

}  // namespace Utils

#endif
