// dev-only; not part of the Chromium build; not in any GN target.
// Minimal stand-in for base::NoDestructor so cursory.cc compiles on the Mac.
#ifndef SCRIPTS_MAC_CPP_BASE_NO_DESTRUCTOR_H_
#define SCRIPTS_MAC_CPP_BASE_NO_DESTRUCTOR_H_

#include <new>
#include <utility>

namespace base {
template <typename T>
class NoDestructor {
 public:
  template <typename... Args>
  explicit NoDestructor(Args&&... args) {
    new (storage_) T(std::forward<Args>(args)...);
  }
  NoDestructor(const NoDestructor&) = delete;
  NoDestructor& operator=(const NoDestructor&) = delete;
  const T& operator*() const { return *get(); }
  T& operator*() { return *get(); }
  const T* operator->() const { return get(); }
  T* operator->() { return get(); }
  T* get() { return reinterpret_cast<T*>(storage_); }
  const T* get() const { return reinterpret_cast<const T*>(storage_); }

 private:
  alignas(T) char storage_[sizeof(T)];
};
}  // namespace base

#endif
