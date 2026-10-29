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
inline std::string fingerprint(const handlegraph::PathHandleGraph& graph) {
    using namespace handlegraph;
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
    path_digest.number(paths.size());
    uint64_t path_steps = 0;
    for (const auto& item : paths) {
        path_handle_t p = item.second;
        path_digest.text(item.first);
        path_digest.number(graph.get_is_circular(p));
        path_digest.number(static_cast<uint64_t>(graph.get_sense(p)));
        path_digest.text(graph.get_sample_name(p));
        path_digest.number(graph.get_haplotype(p));
        path_digest.text(graph.get_locus_name(p));
        path_digest.number(graph.get_phase_block(p));
        auto subrange = graph.get_subrange(p);
        path_digest.number(subrange.first);
        path_digest.number(subrange.second);
        path_digest.number(graph.get_step_count(p));
        graph.for_each_step_in_path(p, [&](step_handle_t step) {
            path_digest.number(traversal(graph, graph.get_handle_of_step(step)));
            ++path_steps;
        });
    }
    std::ostringstream out;
    out << "{\"format\":\"vg-strict-graph-sha256-v1\",\"nodes\":" << nodes.size()
        << ",\"adjacency_entries\":" << adjacency_entries << ",\"paths\":" << paths.size()
        << ",\"path_steps\":" << path_steps
        << ",\"nodes_sha256\":\"" << node_digest.finish()
        << "\",\"edges_sha256\":\"" << edge_digest.finish()
        << "\",\"paths_sha256\":\"" << path_digest.finish() << "\"}";
    return out.str();
}
}}
#endif
