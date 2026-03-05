#ifndef utils_h
#define utils_h 1

#include <string>

/// Shared string-normalization helpers.
namespace Utils {

/// Convert string to lowercase using C-locale byte semantics.
std::string ToLower(std::string value);

/// Trim leading/trailing whitespace.
std::string Trim(std::string value);

/// Remove one matching outer single- or double-quote pair when present.
std::string Unquote(const std::string& value);

}  // namespace Utils

#endif
