#include "subcommand.hpp"
#include <vg/io/vpkg.hpp>
#include <handlegraph/path_handle_graph.hpp>
#include "../algorithms/unchop_fingerprint.hpp"
#include <iostream>

using namespace vg::subcommand;

int main_unchop_fingerprint(int argc, char** argv) {
    if (argc != 3 && !(argc == 5 && std::string(argv[2]) == "--threads")) {
        std::cerr << "usage: vg unchop-fingerprint [--threads N] graph.vg\n";
        return 1;
    }
    size_t threads = 1;
    if (argc == 5) {
        std::string value(argv[3]);
        if (value.empty() || value.find_first_not_of("0123456789") != std::string::npos ||
            !(threads = std::stoull(value))) {
            std::cerr << "threads must be a positive integer\n";
            return 1;
        }
    }
    auto graph = vg::io::VPKG::load_one<handlegraph::PathHandleGraph>(argv[argc - 1]);
    std::cout << vg::unchop_benchmark::fingerprint(*graph, threads) << "\n";
    return 0;
}
static Subcommand vg_unchop_fingerprint("unchop-fingerprint",
    "strict graph fingerprint for the Cactus unchop benchmark", main_unchop_fingerprint);
