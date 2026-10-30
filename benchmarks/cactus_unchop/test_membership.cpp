#include <bdsg/packed_graph.hpp>
#include "unchop_fingerprint.hpp"
#include <map>
#include <random>
#include <iostream>
#include <sstream>
#include <stdexcept>
using namespace handlegraph;

// Compare against independently counted path steps after fragmentation,
// deleted nodes, forced compaction, serialization, and subsequent edits.
void check(bdsg::PackedGraph& g) {
    std::map<nid_t, size_t> expected, observed;
    g.for_each_path_handle([&](path_handle_t p) {
        g.for_each_step_in_path(p, [&](step_handle_t s) { ++expected[g.get_id(g.get_handle_of_step(s))]; });
    });
    g.for_each_handle([&](handle_t h) {
        g.for_each_step_on_handle(h, [&](step_handle_t s) {
            if (g.get_id(g.get_handle_of_step(s)) != g.get_id(h))
                throw std::runtime_error("incorrect membership target");
            ++observed[g.get_id(h)];
        });
        if (expected[g.get_id(h)] != observed[g.get_id(h)])
            throw std::runtime_error("membership count mismatch");
    });
}
int main() {
    for (unsigned seed = 0; seed < 40; ++seed) {
        bdsg::PackedGraph g;
        std::mt19937 rng(seed);
        std::vector<handle_t> nodes;
        for (size_t i = 0; i < 60; ++i) nodes.push_back(g.create_handle("ACGT", 3*i+1));
        std::vector<path_handle_t> paths;
        for (size_t i = 0; i < 30; ++i) {
            auto p = g.create_path_handle("sample#"+std::to_string(i)+"#chr21");
            paths.push_back(p);
            for (size_t j = 0; j < 150; ++j) {
                auto h = nodes[rng()%nodes.size()];
                g.append_step(p, rng()%2 ? h : g.flip(h));
            }
        }
        for (size_t i = 0; i < paths.size(); ++i) {
            if ((i+seed)%3 != 0) g.destroy_path(paths[i]);
        }
        for (size_t i = 0; i < nodes.size(); ++i) {
            if ((i+seed)%5 == 0) g.destroy_handle(nodes[i]);
        }
        check(g);
        g.optimize(false);
        check(g);
        std::stringstream data;
        g.serialize(data);
        bdsg::PackedGraph restored;
        restored.deserialize(data);
        check(restored);
        auto extra = restored.create_path_handle("new#1#chr21");
        restored.for_each_handle([&](handle_t h) { restored.append_step(extra,h); });
        check(restored);
        std::cout << vg::unchop_benchmark::fingerprint(restored,4) << '\n';
    }
    bdsg::PackedGraph empty;
    empty.optimize(false);
    check(empty);
    // Cross three node hashing blocks and exercise parallel node/edge work,
    // then prove that path-uncovered sequence and topology affect identity.
    bdsg::PackedGraph big;
    handle_t previous;
    for (size_t i = 1; i <= 9000; ++i) {
        auto h = big.create_handle(i%2 ? "AC" : "GT",i);
        if (i>1) big.create_edge(previous,h);
        previous=h;
    }
    auto one = vg::unchop_benchmark::fingerprint(big,1);
    if (one != vg::unchop_benchmark::fingerprint(big,8)) throw std::runtime_error("parallel nodes/edges differ");
    auto extra = big.create_handle("A",9999);
    if (one == vg::unchop_benchmark::fingerprint(big,8)) throw std::runtime_error("missed uncovered node");
    one = vg::unchop_benchmark::fingerprint(big,4);
    big.create_edge(previous,big.flip(extra));
    if (one == vg::unchop_benchmark::fingerprint(big,8)) throw std::runtime_error("missed uncovered edge");
}
