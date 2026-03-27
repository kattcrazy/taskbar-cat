def determine_direction(dx, dy, *, h_strong, h_weak, v_threshold):
    """Horizontal and vertical direction labels from mouse delta vs thresholds."""
    if dx < -h_strong:
        h_dir = "left"
        h_intensity = "far"
    elif dx < -h_weak:
        h_dir = "left"
        h_intensity = "normal"
    elif dx < -h_weak // 2:
        h_dir = "left"
        h_intensity = "slight"
    elif dx > h_strong:
        h_dir = "right"
        h_intensity = "far"
    elif dx > h_weak:
        h_dir = "right"
        h_intensity = "normal"
    elif dx > h_weak // 2:
        h_dir = "right"
        h_intensity = "slight"
    else:
        h_dir = "forward"
        h_intensity = "normal"

    # Positive dy means mouse is below cat on screen
    if dy < -v_threshold:
        v_dir = "up"
        v_intensity = "normal"
    elif dy < -v_threshold // 2:
        v_dir = "up"
        v_intensity = "slight"
    elif dy > v_threshold:
        v_dir = "down"
        v_intensity = "normal"
    elif dy > v_threshold // 2:
        v_dir = "down"
        v_intensity = "slight"
    else:
        v_dir = "center"
        v_intensity = "normal"

    return h_dir, h_intensity, v_dir, v_intensity


def find_best_pose(h_dir, h_intensity, v_dir, v_intensity, pose_images):
    """Pick best pose filename stem present in pose_images."""
    candidates = []

    if h_dir == "forward":
        if v_dir == "center":
            candidates = ["forward"]
        else:
            if v_intensity == "slight":
                candidates = [f"forward_slight_{v_dir}", f"forward_{v_dir}", "forward"]
            else:
                candidates = [f"forward_{v_dir}", f"forward_slight_{v_dir}", "forward"]

    elif h_dir in ("left", "right"):
        if h_intensity == "far":
            if v_dir == "center":
                candidates = [f"{h_dir}_{h_dir}", f"{h_dir}", f"{h_dir}_center"]
            else:
                if v_intensity == "slight":
                    candidates = [
                        f"{h_dir}_slight_{v_dir}",
                        f"{h_dir}_{v_dir}",
                        f"{h_dir}_{h_dir}",
                        f"{h_dir}",
                    ]
                else:
                    candidates = [
                        f"{h_dir}_{v_dir}",
                        f"{h_dir}_slight_{v_dir}",
                        f"{h_dir}_{h_dir}",
                        f"{h_dir}",
                    ]
        elif h_intensity == "slight":
            if v_dir == "center":
                candidates = [
                    f"forward_{h_dir}",
                    f"{h_dir}",
                    f"{h_dir}_center",
                    "forward",
                ]
            else:
                forward_side = f"forward_{h_dir}"
                if v_intensity == "slight":
                    candidates = [
                        f"{forward_side}_slight_{v_dir}",
                        f"{forward_side}_{v_dir}",
                        f"{forward_side}",
                        f"{h_dir}_slight_{v_dir}",
                        f"{h_dir}_{v_dir}",
                        f"{h_dir}",
                        f"forward_slight_{v_dir}",
                        f"forward_{v_dir}",
                        "forward",
                    ]
                else:
                    candidates = [
                        f"{forward_side}_{v_dir}",
                        f"{forward_side}_slight_{v_dir}",
                        f"{forward_side}",
                        f"{h_dir}_{v_dir}",
                        f"{h_dir}_slight_{v_dir}",
                        f"{h_dir}",
                        f"forward_{v_dir}",
                        f"forward_slight_{v_dir}",
                        "forward",
                    ]
        else:
            if v_dir == "center":
                candidates = [f"{h_dir}", f"{h_dir}_center"]
            else:
                if v_intensity == "slight":
                    candidates = [
                        f"{h_dir}_slight_{v_dir}",
                        f"{h_dir}_{v_dir}",
                        f"{h_dir}",
                    ]
                else:
                    candidates = [
                        f"{h_dir}_{v_dir}",
                        f"{h_dir}_slight_{v_dir}",
                        f"{h_dir}",
                    ]

    for candidate in candidates:
        if candidate in pose_images:
            return candidate

    if "forward" in pose_images:
        return "forward"
    if len(pose_images) > 0:
        return list(pose_images.keys())[0]
    return None
