#include "gfa_numeric_ids.hpp"
#include <stdexcept>
#include <unordered_map>
#include <iostream>

using vg::algorithms::NumericGfaIds;
void require(bool value) { if (!value) throw std::runtime_error("numeric ID check failed"); }
int main() {
    require(NumericGfaIds::parse("1") == 1);
    require(NumericGfaIds::parse("9223372036854775807") == INT64_MAX);
    for (const char* text : {"", "0", "01", "-1", "+1", "a", "12x", "9223372036854775808"})
        require(NumericGfaIds::parse(text) == 0);
    NumericGfaIds ids(true);
    require(ids.insert(1) && ids.insert(3));
    require(!ids.insert(1));
    require(ids.contains(1) && !ids.contains(2) && ids.contains(3));
    // The same forward reference becomes valid only after its S line arrives.
    require(ids.insert(2) && ids.contains(2));
    require(ids.insert(20000000) && !ids.contains(19999999));
    std::unordered_map<std::string, int64_t> names;
    ids.materialize(names);
    require(!ids.active() && names.size() == 4);
    require(names.at("1") == 1 && names.at("2") == 2 && names.at("3") == 3);
    require(names.at("20000000") == 20000000 && names.count("01") == 0);
    std::cout << "PASS: decimal bounds, canonical names, duplicate/hole/forward-reference lookup, fallback map\n";
}
