#include <sdsl/int_vector.hpp>
#include <sdsl/io.hpp>
#include <sstream>
#include <iostream>
#include <stdexcept>

int main() {
    sdsl::int_vector<> values(1003, 0, 17);
    for (size_t i = 0; i < values.size(); ++i) values[i] = (i * 79) % 65537;
    std::ostringstream bare, with_tree;
    values.serialize(bare);
    sdsl::structure_tree_node tree("root", "test");
    values.serialize(with_tree, &tree, "values");
    if (bare.str() != with_tree.str() || tree.children.empty() ||
        tree.children.begin()->second->size == 0)
        throw std::runtime_error("serialization or requested structure tree changed");
    std::istringstream input(bare.str());
    sdsl::int_vector<> restored;
    restored.load(input);
    if (restored != values) throw std::runtime_error("serialization roundtrip failed");
    std::cout.write(bare.str().data(), bare.str().size());
}
