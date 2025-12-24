#pragma once

// Compatibility header for using Qt types with std::unordered_map/set
// Qt6 provides std::hash<QString> in qhashfunctions.h, but not for QUuid

#include <QUuid>
#include <functional>

namespace std {
    template<>
    struct hash<QUuid> {
        size_t operator()(const QUuid& uuid) const noexcept {
            return qHash(uuid);
        }
    };
}
