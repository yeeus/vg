#include <bdsg/packed_graph.hpp>
#include <handlegraph/algorithms/chop.hpp>
#include "unchop_fingerprint.hpp"
#include <cstdlib>
#include <iostream>
#include <map>
#include <random>
#include <stdexcept>

using namespace handlegraph;
using bdsg::PackedGraph;

std::map<std::string, std::string> sequences(const PackedGraph& graph) {
    std::map<std::string, std::string> result;
    graph.for_each_path_handle([&](path_handle_t p) {
        std::string seq;
        graph.for_each_step_in_path(p, [&](step_handle_t s) {
            seq += graph.get_sequence(graph.get_handle_of_step(s));
        });
        result[graph.get_path_name(p)] = seq;
    });
    return result;
}

void path(PackedGraph& graph, const std::string& name, const std::vector<handle_t>& walk,
          bool circular = false) {
    auto p = graph.create_path_handle(name, circular);
    for (size_t i = 0; i < walk.size(); ++i) {
        graph.append_step(p, walk[i]);
        if (i) graph.create_edge(walk[i - 1], walk[i]);
    }
    if (circular && !walk.empty()) graph.create_edge(walk.back(), walk.front());
}

void fixture(PackedGraph& graph, unsigned seed) {
    std::vector<handle_t> h;
    for (int i = 0; i < (seed % 8 == 0 ? 512 : 12); ++i)
        h.push_back(graph.create_handle(i % 2 ? "CG" : "AT", 3 * i + 1));
    switch (seed % 8) {
    case 0: {
        std::vector<handle_t> walk = h;
        path(graph, "sample#1#chr21", walk);
        std::vector<handle_t> reverse;
        for (auto i = walk.rbegin(); i != walk.rend(); ++i) reverse.push_back(graph.flip(*i));
        path(graph, "sample#2#chr21", reverse);
        for (unsigned p = 3; p <= 32; ++p)
            path(graph, "sample#" + std::to_string(p) + "#chr21", p % 2 ? walk : reverse);
        break;
    }
    case 1:
        path(graph, "cycle#1#chr21", {h[0], h[1], h[2]}, true);
        path(graph, "self#1#chr21", {h[3], h[3]});
        break;
    case 2:
        path(graph, "a#1#chr21", {h[0], h[1], h[3], h[4]});
        path(graph, "b#1#chr21", {h[0], h[2], h[3], h[4]});
        path(graph, "empty", {});
        break;
    case 3:
        path(graph, "a#1#chr21", {h[0], graph.flip(h[1]), h[2], h[3]});
        path(graph, "b#1#chr21", {graph.flip(h[3]), graph.flip(h[2]), h[1], graph.flip(h[0])});
        break;
    case 4:
        path(graph, "a#1#chr21", {h[0], h[1], h[0], h[1], h[2]});
        path(graph, "b#1#chr21", {h[0], h[1], h[2]});
        break;
    case 5:
        path(graph, "long#1#chr21", {h[0], h[1], h[2], h[3]});
        path(graph, "start_inside#1#chr21", {h[1], h[2]});
        path(graph, "end_inside#1#chr21", {h[0], h[1]});
        break;
    case 6:
        // Path-uncovered topology must participate in the comparison.
        graph.create_edge(h[0], h[1]); graph.create_edge(h[1], h[2]);
        graph.create_edge(h[4], graph.flip(h[5]));
        break;
    default: {
        std::mt19937 rng(seed);
        for (unsigned p = 0; p < 9; ++p) {
            std::vector<handle_t> walk;
            for (unsigned j = 0; j < 30; ++j) {
                handle_t node = h[rng() % h.size()];
                walk.push_back(rng() % 2 ? node : graph.flip(node));
            }
            path(graph, "random#" + std::to_string(p) + "#chr21", walk);
        }
    }
    }
}

int main(int argc, char** argv) {
    size_t threads = argc > 1 ? std::stoul(argv[1]) : 1;
    bool roundtrip = argc > 2 && std::string(argv[2]) == "roundtrip";
    vg::unchop_benchmark::Digest known;
    known.bytes("abc", 3);
    if (known.finish() != "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
        throw std::runtime_error("SHA256 known vector failed");
    for (unsigned seed = 0; seed < 80; ++seed) {
        std::unique_ptr<PackedGraph> storage(new PackedGraph);
        fixture(*storage, seed);
        if (roundtrip) {
            std::stringstream stream;
            storage->serialize(stream);
            storage.reset(new PackedGraph);
            storage->deserialize(stream);
        }
        auto& graph = *storage;
        auto before = sequences(graph);
#ifdef BENCH_PARALLEL_API
        algorithms::unchop(graph, threads);
#else
        if (threads != 1) throw std::runtime_error("control requires one thread");
        algorithms::unchop(graph);
#endif
        // Original unchop can drop closed circular paths. Keep those fixtures
        // as differential characterization, not a claim to fix that behavior.
        if (seed % 8 != 1 && sequences(graph) != before) {
            std::cerr << "seed=" << seed << "\n";
            for (const auto& p : before) std::cerr << p.first << " before=" << p.second << " after=" << sequences(graph).at(p.first) << "\n";
            throw std::runtime_error("Path sequence changed");
        }
        std::cout << seed << "\t" << vg::unchop_benchmark::fingerprint(graph) << "\n";
    }
    PackedGraph coverage;
    auto a = coverage.create_handle("A", 1);
    auto b = coverage.create_handle("C", 2);
    path(coverage, "p", {a});
    std::string before = vg::unchop_benchmark::fingerprint(coverage);
    coverage.create_edge(a, b);
    if (before == vg::unchop_benchmark::fingerprint(coverage))
        throw std::runtime_error("Fingerprint missed a path-uncovered edge");
    std::cerr << "PASS: 80 PackedGraph cases, linear-path sequence invariants, SHA256 vector, uncovered-edge detection\n";
}


