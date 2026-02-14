#include "utils.hh"

#include <algorithm>
#include <cctype>

namespace Utils {

std::string ToLower(std::string value) {
  std::transform(value.begin(), value.end(), value.begin(),
                 [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
  return value;
}

std::string Trim(std::string value) {
  const auto isSpace = [](unsigned char c) { return std::isspace(c) != 0; };

  value.erase(value.begin(),
              std::find_if(value.begin(), value.end(),
                           [&](char c) { return !isSpace(static_cast<unsigned char>(c)); }));

  value.erase(
      std::find_if(value.rbegin(), value.rend(),
                   [&](char c) { return !isSpace(static_cast<unsigned char>(c)); })
          .base(),
      value.end());

  return value;
}

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
