#include "utils.hh"

#include <algorithm>
#include <cctype>

namespace Utils {

/**
 * Lowercase an ASCII/byte string in-place and return the normalized result.
 *
 * Implementation notes:
 * - Uses std::transform for single-pass mutation over the string buffer.
 * - Performs unsigned-char cast prior to std::tolower for portability/safety.
 */
std::string ToLower(std::string value) {
  std::transform(value.begin(), value.end(), value.begin(),
                 [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
  return value;
}

/**
 * Trim leading and trailing whitespace from a mutable string copy.
 *
 * Algorithm:
 * 1. Find first non-space from the front and erase prefix.
 * 2. Find first non-space from the back and erase suffix.
 *
 * This handles all-whitespace inputs safely (result becomes empty string).
 */
std::string Trim(std::string value) {
  const auto isSpace = [](unsigned char c) { return std::isspace(c) != 0; };

  // Remove left-side whitespace.
  value.erase(value.begin(),
              std::find_if(value.begin(), value.end(),
                           [&](char c) { return !isSpace(static_cast<unsigned char>(c)); }));

  // Remove right-side whitespace.
  value.erase(
      std::find_if(value.rbegin(), value.rend(),
                   [&](char c) { return !isSpace(static_cast<unsigned char>(c)); })
          .base(),
      value.end());

  return value;
}

/**
 * Remove one matching outer quote layer from the provided string.
 *
 * We intentionally strip only one layer so callers can control whether further
 * normalization is desirable.
 */
std::string Unquote(const std::string& value) {
  if (value.size() < 2) {
    return value;
  }

  const char first = value.front();
  const char last = value.back();
  if ((first == '"' && last == '"') || (first == '\'' && last == '\'')) {
    return value.substr(1, value.size() - 2);
  }

  return value;
}

}  // namespace Utils
