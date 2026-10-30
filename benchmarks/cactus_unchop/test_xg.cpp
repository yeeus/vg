#include "xg.hpp"
#include <bdsg/packed_graph.hpp>
#include "unchop_fingerprint.hpp"
#include <algorithm>
#include <cstdlib>
#include <sstream>
#include <stdexcept>

using namespace handlegraph;
int main(int argc, char** argv) {
    if (argc != 2) return 2;
    if (std::string(argv[1]) == "control") unsetenv("VG_BENCH_XG_MODE");
    else setenv("VG_BENCH_XG_MODE", argv[1], 1);
    omp_set_num_threads(2);
    for (unsigned seed = 0; seed < 14; ++seed) {
        bdsg::PackedGraph input;
        std::vector<handle_t> nodes;
        for (size_t i = 0; i < 11; ++i)
            nodes.push_back(input.create_handle(i % 2 ? "ACGT" : "T", 3 * i + 1));
        for (unsigned p = 0; p < (seed == 12 ? 0 : seed == 13 ? 1 : 9); ++p) {
            auto path = input.create_path_handle("sample#" + std::to_string(p) + "#chr21", p == 7);
            handle_t previous;
            for (size_t j = 0; j < (p == 8 || seed == 13 ? 0 : 19 + seed); ++j) {
                auto h = nodes[(j * (seed + 1) + p) % 9];
                if ((p + j) % 3 == 0) h = input.flip(h);
                if (j) input.create_edge(previous, h);
                input.append_step(path, h);
                previous = h;
            }
            if (p == 7) input.create_edge(previous, input.get_handle_of_step(input.path_begin(path)));
        }
        input.create_edge(nodes[9], input.flip(nodes[10])); // uncovered topology
        xg::XG graph;
        graph.from_path_handle_graph(input);
        std::string strict = vg::unchop_benchmark::fingerprint(graph, 4);
        vg::unchop_benchmark::Digest index;
        for (auto h : nodes) {
            std::vector<std::tuple<std::string, uint64_t, bool, uint64_t>> records;
            graph.for_each_step_position_on_handle(graph.get_handle(input.get_id(h)),
                [&](const step_handle_t& step, const bool& reverse, const uint64_t& position) {
                    records.emplace_back(graph.get_path_name(graph.get_path_handle_of_step(step)),
                                         as_integers(step)[1], reverse, position);
                    return true;
                });
            std::sort(records.begin(), records.end());
            index.number(input.get_id(h));
            index.number(records.size());
            for (const auto& r : records) {
                index.text(std::get<0>(r)); index.number(std::get<1>(r));
                index.number(std::get<2>(r)); index.number(std::get<3>(r));
            }
        }
        graph.for_each_path_handle([&](path_handle_t path) {
            size_t position = 0;
            graph.for_each_step_in_path(path, [&](step_handle_t step) {
                if (graph.get_position_of_step(step) != position ||
                    graph.get_step_at_position(path, position) != step)
                    throw std::runtime_error("XG position query mismatch");
                position += graph.get_length(graph.get_handle_of_step(step));
            });
        });
        std::ostringstream bytes;
        graph.serialize(bytes);
        vg::unchop_benchmark::Digest serialized;
        const std::string data = bytes.str();
        serialized.bytes(data.data(), data.size());
        std::cout << seed << '\t' << strict << '\t' << index.finish() << '\t' << serialized.finish() << '\n';
    }
}
