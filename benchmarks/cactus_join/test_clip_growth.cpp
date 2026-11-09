// Exercise path-vector growth and the Full/Clip creation of replacement paths.
#include <bdsg/packed_graph.hpp>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

using namespace handlegraph;

int main(int argc, char** argv) {
    if (argc != 4) throw std::runtime_error("usage: test_clip_growth full|clip nodes sample_paths");
    const std::string mode = argv[1];
    if (mode != "full" && mode != "clip") throw std::runtime_error("unknown mode");
    const size_t count = std::stoull(argv[2]), samples = std::stoull(argv[3]);
    if (count < 4 || samples < 2) throw std::runtime_error("fixture too small");
    bdsg::PackedGraph graph;
    std::vector<handle_t> walk;
    for (size_t i = 0; i < count; ++i) {
        walk.push_back(graph.create_handle("A"));
        if (i) graph.create_edge(walk[i - 1], walk[i]);
    }
    const auto insertion = graph.create_handle(std::string(12000, 'G'));
    graph.create_edge(walk[count / 2 - 1], insertion);
    graph.create_edge(insertion, walk[count / 2]);
    auto append = [&](path_handle_t path, bool alternate) {
        for (size_t i = 0; i < count; ++i) {
            if (alternate && i == count / 2) graph.append_step(path, insertion);
            graph.append_step(path, walk[i]);
        }
    };
    append(graph.create_path_handle("GRCh38#0#chr21"), false);
    append(graph.create_path_handle("_MINIGRAPH_#0#chr21"), mode == "full");
    for (size_t i = 0; i < samples; ++i) {
        append(graph.create_path_handle("sample" + std::to_string(i) + "#1#chr21"), mode == "clip");
    }
    // Reloading gives the path vector exactly its saved size, as in production.
    // Each clipping command must grow it to add its replacement subpaths.
    graph.serialize(std::cout);
}
