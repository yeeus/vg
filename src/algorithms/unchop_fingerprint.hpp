#ifndef VG_UNCHOP_FINGERPRINT_HPP
#define VG_UNCHOP_FINGERPRINT_HPP

#include <handlegraph/path_handle_graph.hpp>
#include <openssl/evp.h>
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <vector>
#include <atomic>
#include <future>

namespace vg { namespace unchop_benchmark {

class Digest {
    std::unique_ptr<EVP_MD_CTX, decltype(&EVP_MD_CTX_free)> ctx;
    std::array<unsigned char, 65536> buffer;
    size_t used = 0;
    void flush() {
        if (used && EVP_DigestUpdate(ctx.get(), buffer.data(), used) != 1)
            throw std::runtime_error("SHA256 update failed");
        used = 0;
    }
public:
    Digest() : ctx(EVP_MD_CTX_new(), EVP_MD_CTX_free) {
        if (!ctx || EVP_DigestInit_ex(ctx.get(), EVP_sha256(), nullptr) != 1)
            throw std::runtime_error("SHA256 initialization failed");
    }
    void bytes(const void* data, size_t length) {
        auto* cursor = static_cast<const unsigned char*>(data);
        while (length) {
            size_t n = std::min(length, buffer.size() - used);
            std::memcpy(buffer.data() + used, cursor, n);
            used += n; cursor += n; length -= n;
            if (used == buffer.size()) flush();
        }
    }
    void number(uint64_t value) {
        unsigned char data[8];
        for (size_t i = 0; i < 8; ++i) data[i] = (value >> (8 * i)) & 255;
        bytes(data, sizeof(data));
    }
    void text(const std::string& value) { number(value.size()); bytes(value.data(), value.size()); }
    std::string finish() {
        flush();
        unsigned char result[EVP_MAX_MD_SIZE];
        unsigned int size = 0;
        if (EVP_DigestFinal_ex(ctx.get(), result, &size) != 1)
            throw std::runtime_error("SHA256 finalization failed");
        std::ostringstream out;
        for (unsigned int i = 0; i < size; ++i)
            out << std::hex << std::setfill('0') << std::setw(2) << unsigned(result[i]);
        return out.str();
    }
};

inline uint64_t traversal(const handlegraph::PathHandleGraph& graph,
                          const handlegraph::handle_t& handle) {
    return (uint64_t(graph.get_id(handle)) << 1) | uint64_t(graph.get_is_reverse(handle));
}

// Strict identity: node IDs/sequence, both orientations of all adjacency lists,
// and complete path metadata and ordered steps. Includes path-uncovered topology.
// Storage layout, allocated capacity and serialization order are excluded.
inline std::string fingerprint(const handlegraph::PathHandleGraph& graph, size_t threads = 1) {
    using namespace handlegraph;
    if (!threads) throw std::invalid_argument("fingerprint requires at least one thread");
    std::vector<handle_t> nodes;
    nodes.reserve(graph.get_node_count());
    graph.for_each_handle([&](const handle_t& h) { nodes.push_back(graph.forward(h)); });
    std::sort(nodes.begin(), nodes.end(), [&](handle_t a, handle_t b) {
        return graph.get_id(a) < graph.get_id(b);
    });
    Digest node_digest, edge_digest, path_digest;
    node_digest.number(nodes.size());
    edge_digest.number(nodes.size());
    uint64_t adjacency_entries = 0;
    for (handle_t node : nodes) {
        node_digest.number(graph.get_id(node));
        node_digest.text(graph.get_sequence(node));
        for (size_t reverse = 0; reverse < 2; ++reverse) {
            handle_t from = reverse ? graph.flip(node) : node;
            std::vector<uint64_t> neighbors;
            graph.follow_edges(from, false, [&](handle_t to) { neighbors.push_back(traversal(graph, to)); });
            std::sort(neighbors.begin(), neighbors.end());
            edge_digest.number(traversal(graph, from));
            edge_digest.number(neighbors.size());
            for (uint64_t to : neighbors) edge_digest.number(to);
            adjacency_entries += neighbors.size();
        }
    }
    std::vector<std::pair<std::string, path_handle_t>> paths;
    graph.for_each_path_handle([&](path_handle_t p) { paths.emplace_back(graph.get_path_name(p), p); });
    std::sort(paths.begin(), paths.end(), [](const auto& a, const auto& b) { return a.first < b.first; });
    // Hash paths independently, then combine the fixed-size digests in sorted
    // name order. Memory is one loaded graph plus O(nodes + paths + threads),
    // never a buffer containing every path step or a second copy of the graph.
    std::vector<std::pair<std::string, uint64_t>> path_hashes(paths.size());
    auto hash_path = [&](size_t index) {
        const auto& item = paths[index];
        path_handle_t p = item.second;
        Digest digest;
        digest.text(item.first);
        digest.number(graph.get_is_circular(p));
        digest.number(static_cast<uint64_t>(graph.get_sense(p)));
        digest.text(graph.get_sample_name(p));
        digest.number(graph.get_haplotype(p));
        digest.text(graph.get_locus_name(p));
        digest.number(graph.get_phase_block(p));
        auto subrange = graph.get_subrange(p);
        digest.number(subrange.first);
        digest.number(subrange.second);
        digest.number(graph.get_step_count(p));
        uint64_t steps = 0;
        graph.for_each_step_in_path(p, [&](step_handle_t step) {
            digest.number(traversal(graph, graph.get_handle_of_step(step)));
            ++steps;
        });
        path_hashes[index] = {digest.finish(), steps};
    };
    threads = std::min(threads, std::max<size_t>(1, paths.size()));
    if (threads == 1) {
        for (size_t i = 0; i < paths.size(); ++i) hash_path(i);
    } else {
        std::atomic<size_t> next_path(0);
        auto worker = [&]() {
            for (size_t i = next_path.fetch_add(1); i < paths.size(); i = next_path.fetch_add(1))
                hash_path(i);
        };
        std::vector<std::future<void>> workers;
        for (size_t i = 1; i < threads; ++i)
            workers.emplace_back(std::async(std::launch::async, worker));
        worker();
        for (auto& thread : workers) thread.get();
    }
    path_digest.number(paths.size());
    uint64_t path_steps = 0;
    for (const auto& item : path_hashes) {
        path_digest.text(item.first);
        path_steps += item.second;
    }
    std::ostringstream out;
    out << "{\"format\":\"vg-strict-graph-sha256-v2\",\"nodes\":" << nodes.size()
        << ",\"adjacency_entries\":" << adjacency_entries << ",\"paths\":" << paths.size()
        << ",\"path_steps\":" << path_steps
        << ",\"nodes_sha256\":\"" << node_digest.finish()
        << "\",\"edges_sha256\":\"" << edge_digest.finish()
        << "\",\"paths_sha256\":\"" << path_digest.finish() << "\"}";
    return out.str();
}
}}
#endif
