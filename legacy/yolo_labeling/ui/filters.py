"""Filtering the working set by class, size, overlap and IoU.

Extracted from the original single-file `yolo_labeling_tool.py`. Implemented as a
mixin so every `self.*` reference keeps working unchanged through the MRO.
"""

from __future__ import annotations

import os
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import cv2

from yolo_labeling.core import badscan as _badscan
from yolo_labeling.core import geometry as _geom
from yolo_labeling.core import labelio as _labelio
from yolo_labeling.core import predcache as _predcache
from yolo_labeling.core import ranges as _ranges


class FiltersMixin:
    def toggle_class_filter(self):
        """Toggle class filter on/off"""
        self.filter_by_class_enabled = self.filter_class_var.get()
        if self.filter_by_class_enabled:
            self.filter_class_combo.config(state='readonly')
        else:
            self.filter_class_combo.config(state='disabled')

    def toggle_size_filter(self):
        """Toggle size filter on/off"""
        self.filter_by_size_enabled = self.filter_size_var.get()

    def toggle_relsize_filter(self):
        """Toggle relative (percentage-of-image) size filter on/off"""
        self.filter_by_relsize_enabled = self.filter_relsize_var.get()

    def toggle_review_filter(self):
        """Toggle the reviewed/not-reviewed filter on/off"""
        self.filter_by_review_enabled = self.filter_review_var.get()

    def toggle_name_filter(self):
        """Toggle filename filter on/off"""
        self.filter_by_name_enabled = self.filter_name_var.get()

    def toggle_overlap_filter(self):
        """Toggle overlapping boxes filter on/off"""
        self.filter_by_overlap_enabled = self.filter_overlap_var.get()

    def overlap_pair_counts(self, cls_a, cls_b):
        """Whether a pair of classes counts as an overlap under the current scope.

        Shared by the filter and the red highlighter. They used to hardcode
        `cls1 != cls2` independently, so any change to one silently disagreed
        with the other -- the filter would select an image the highlighter then
        drew nothing on.
        """
        scope = getattr(self, 'filter_overlap_scope', 'different')
        if scope == 'same':
            return cls_a == cls_b
        if scope == 'any':
            return True
        return cls_a != cls_b

    def overlap_iou_in_range(self, iou):
        """Whether a pair's IoU falls in the overlap range. Both ends inclusive.

        Shared by the filter and the red highlighter for the same reason
        `overlap_pair_counts` is. Inclusive at the top because two identical
        boxes are exactly 1.0, and `0.99 - 1.00` is how exact duplicates are
        isolated. Never clamps: an unreachable floor must stay unreachable.
        """
        return (self.filter_overlap_threshold <= iou
                <= getattr(self, 'filter_overlap_max', 1.0))

    def _on_overlap_scope_change(self):
        """Radio handler: adopt the scope and refresh the red highlighting."""
        self.filter_overlap_scope = self.filter_overlap_scope_var.get()
        self.save_class_config()
        if getattr(self, 'highlight_overlaps', False):
            self.detect_current_overlaps()
            self.display_image()

    def toggle_presence_filter(self):
        """Toggle class presence/absence filter on/off"""
        self.filter_by_class_presence_enabled = self.filter_presence_var.get()

    def populate_presence_filter_checkboxes(self):
        """Populate checkboxes for class presence/absence filter"""
        # Clear existing checkboxes
        for widget in self.must_have_checkboxes_frame.winfo_children():
            widget.destroy()
        for widget in self.must_not_have_checkboxes_frame.winfo_children():
            widget.destroy()
        
        self.must_have_class_vars.clear()
        self.must_not_have_class_vars.clear()
        
        # Create checkboxes for each class
        classes = sorted(self.class_info.keys())
        for class_id in classes:
            class_name = self.class_info[class_id]['name']
            
            # Must have checkbox
            var_have = tk.BooleanVar(value=False)
            self.must_have_class_vars[class_id] = var_have
            cb_have = ttk.Checkbutton(
                self.must_have_checkboxes_frame,
                text=f"{class_id}: {class_name}",
                variable=var_have,
                command=self.update_presence_filter
            )
            cb_have.pack(anchor=tk.W, padx=5, pady=1)
            
            # Must NOT have checkbox
            var_not_have = tk.BooleanVar(value=False)
            self.must_not_have_class_vars[class_id] = var_not_have
            cb_not_have = ttk.Checkbutton(
                self.must_not_have_checkboxes_frame,
                text=f"{class_id}: {class_name}",
                variable=var_not_have,
                command=self.update_presence_filter
            )
            cb_not_have.pack(anchor=tk.W, padx=5, pady=1)
        
        # Update scroll regions
        self.must_have_checkboxes_frame.update_idletasks()
        self.must_not_have_checkboxes_frame.update_idletasks()
        self.must_have_canvas.configure(scrollregion=self.must_have_canvas.bbox("all"))
        self.must_not_have_canvas.configure(scrollregion=self.must_not_have_canvas.bbox("all"))

    def update_presence_filter(self):
        """Update the sets of must-have and must-not-have classes"""
        self.filter_must_have_classes.clear()
        self.filter_must_not_have_classes.clear()
        
        for class_id, var in self.must_have_class_vars.items():
            if var.get():
                self.filter_must_have_classes.add(class_id)
        
        for class_id, var in self.must_not_have_class_vars.items():
            if var.get():
                self.filter_must_not_have_classes.add(class_id)

    def update_class_filter_dropdown(self):
        """Update the class filter dropdown with available classes"""
        classes = list(self.class_info.keys())
        class_names = [f"{cid}: {self.class_info[cid]['name']}" for cid in classes]
        self.filter_class_combo['values'] = class_names
        if class_names:
            self.filter_class_combo.current(0)

    def _persisted_filter_state(self):
        """Every filter setting `save_class_config` writes, as one comparable value.

        The save-on-change check used to compare the scope and the overlap floor
        only, so changing anything added later -- the overlap max, say -- was
        silently not saved. One list, read by both sides of the comparison.
        """
        return tuple(getattr(self, name, None) for name in (
            'filter_overlap_scope', 'filter_overlap_threshold', 'filter_overlap_max',
            'filter_iou_direction', 'filter_iou_threshold',
            'filter_iou_conf_lo', 'filter_iou_conf_hi'))

    @staticmethod
    def _read_unit_var(var, current, lo=0.0, hi=1.0):
        """A fraction from an entry: junk keeps `current`, out of range clamps.

        The entry is rewritten whenever the value it shows is not the value in
        force, so the panel never says one thing while the filter uses another.
        """
        value = _ranges.parse_unit(var.get())
        if value is None:
            value = current
        else:
            value = min(max(value, lo), hi)
        if _ranges.parse_unit(var.get()) != value:
            var.set(f"{value:g}")
        return value

    def update_filter(self, event=None):
        """Update filter parameters"""
        # Some of these settings outlive the session, so note them to see
        # whether this call is worth a config write -- update_filter fires on
        # FocusOut of every entry in the panel, most of which change nothing.
        persisted_before = self._persisted_filter_state()

        # Update class filter
        if self.filter_by_class_enabled:
            selected = self.filter_class_combo.get()
            if selected:
                try:
                    # Extract class ID from the format "ID: Name"
                    cls_id = int(selected.split(':', 1)[0].strip())
                    self.filter_class_id = cls_id
                except (ValueError, IndexError):
                    # Handle invalid format or empty string
                    pass
        
        # Update size filter
        try:
            self.filter_min_size = int(self.min_size_var.get())
        except ValueError:
            self.filter_min_size = 0
            self.min_size_var.set("0")
            
        try:
            self.filter_max_size = int(self.max_size_var.get())
        except ValueError:
            self.filter_max_size = 100000
            self.max_size_var.set("100000")

        # Relative size, as a percentage of the image. Four near-identical
        # parses, so a loop rather than four copies of the block above.
        for attr, var, default in (
                ('filter_min_w_pct', self.min_w_pct_var, 0.0),
                ('filter_max_w_pct', self.max_w_pct_var, 100.0),
                ('filter_min_h_pct', self.min_h_pct_var, 0.0),
                ('filter_max_h_pct', self.max_h_pct_var, 100.0)):
            try:
                setattr(self, attr, float(var.get()))
            except ValueError:
                setattr(self, attr, default)
                var.set(f"{default:g}")

        # Reviewed state: 'all' | 'reviewed' | 'unreviewed'
        self.filter_review_state = self.filter_review_state_var.get()

        # Label/Prediction IoU: direction, matching IoU and its own confidence
        # range. The floor cannot go below the cache floor -- nothing exists
        # there -- and a reversed range is refused at Apply, not here.
        self.filter_iou_direction = self.filter_iou_direction_var.get()
        self.filter_iou_threshold = self._read_unit_var(
            self.iou_thresh_var, self.filter_iou_threshold)
        self.filter_iou_conf_lo = self._read_unit_var(
            self.iou_conf_lo_var, self.filter_iou_conf_lo, lo=_predcache.CONF_FLOOR)
        self.filter_iou_conf_hi = self._read_unit_var(
            self.iou_conf_hi_var, self.filter_iou_conf_hi)

        self.filter_overlap_scope = self.filter_overlap_scope_var.get()

        # Overlap IoU range. Junk keeps the previous value, out-of-range is
        # clamped, and a reversed range is left exactly as typed -- people edit
        # one end at a time -- to be refused, by name, at Apply.
        self.filter_overlap_threshold = self._read_unit_var(
            self.filter_overlap_threshold_var, self.filter_overlap_threshold)
        self.filter_overlap_max = self._read_unit_var(
            self.filter_overlap_max_var, getattr(self, 'filter_overlap_max', 1.0))
        # Re-detect overlaps if highlight mode is on
        if self.highlight_overlaps:
            self.detect_current_overlaps()
            self.display_image()

        # Update filename filter
        self.filter_name_text = self.filter_name_text_var.get()
        self.filter_name_case_sensitive = self.filter_name_case_var.get()

        if self._persisted_filter_state() != persisted_before:
            self.save_class_config()

    def _filter_range_error(self):
        """Why an enabled filter's range cannot be applied, or None."""
        if self.filter_by_overlap_enabled:
            error = _ranges.range_error(
                self.filter_overlap_threshold,
                getattr(self, 'filter_overlap_max', 1.0), "Overlap IoU")
            if error:
                return error
        if self.filter_by_iou_enabled:
            error = _ranges.range_error(
                self.filter_iou_conf_lo, self.filter_iou_conf_hi,
                "Prediction confidence", lo_min=_predcache.CONF_FLOOR)
            if error:
                return error
            if self.pred_cache is None and not self.model_predictions_cache:
                # The entry used to be disabled instead -- permanently, since
                # setup runs before any model loads.
                return ("Label/Prediction IoU needs predictions: load a model "
                        "in Setup, then Infer all.")
        return None

    def apply_filters(self):
        """Apply all active filters to image paths, with progress and ETA."""
        if not self.image_paths:
            self.filter_result_var.set("No images loaded")
            return

        # A reversed range is a normal state mid-edit, so it is only refused
        # here, by name -- never swapped while being typed.
        error = self._filter_range_error()
        if error:
            self.filter_result_var.set(error)
            return

        # Check if any filter requiring labels is enabled
        # NOTE: the review-state filter is deliberately absent here. Anything
        # listed sends every image down the label branch below, which silently
        # drops images that have no .txt at all -- and "not yet reviewed" is
        # exactly when you most want to see those.
        requires_labels = (self.filter_by_class_enabled or self.filter_by_size_enabled or
                          self.filter_by_iou_enabled or self.filter_by_class_presence_enabled or
                          self.filter_by_overlap_enabled or self.filter_by_relsize_enabled)
        
        if requires_labels and not self.label_folder and not hasattr(self, 'per_image_label_folders'):
            self.filter_result_var.set("Label folder not set (required for class/size/IOU/presence/overlap filters)")
            return
            
        self.progress_var.set(0)
        self.filter_result_var.set("Filtering...")
        self.root.update_idletasks()
        self.filtered_image_paths = []
        total_checked = 0
        total_images = len(self.image_paths)
        start_time = time.time()
        # Never-labelled frames are exactly where unlabelled objects live, so
        # a direction that looks for predictions with no label must see them.
        include_unlabelled = (self.filter_by_iou_enabled and
                              getattr(self, 'filter_iou_direction', 'either') != 'labels')
        self._begin_iou_filter_pass()
        
        # Pre-compute label folder mapping for faster lookup
        label_folder_map = {}
        if hasattr(self, 'per_image_label_folders'):
            for img_folder, lbl_folder in self.per_image_label_folders.items():
                label_folder_map[img_folder] = lbl_folder
        
        # Pre-build a set of image paths that have labels (if cache is empty)
        # This avoids calling .exists() repeatedly in the loop
        has_label_set = set()
        if requires_labels and not self.labels_cache:
            self.filter_result_var.set("Checking which images have labels...")
            self.root.update_idletasks()
            
            # Build set of images with labels (single pass)
            for img_path in self.image_paths:
                img_path_str = str(img_path)
                label_path = None
                
                if self.label_folder:
                    label_path = Path(self.label_folder) / f"{img_path.stem}.txt"
                else:
                    for img_folder, lbl_folder in label_folder_map.items():
                        if img_path_str.startswith(img_folder):
                            label_path = Path(lbl_folder) / f"{img_path.stem}.txt"
                            break
                
                if label_path and label_path.exists():
                    has_label_set.add(img_path_str)
        
        # Process in batches with less frequent UI updates
        batch_size = 100
        ui_update_interval = 200  # Update UI every N images instead of every 10
        
        for batch_idx in range(0, total_images, batch_size):
            batch_end = min(batch_idx + batch_size, total_images)
            batch = self.image_paths[batch_idx:batch_end]
            
            for i, img_path in enumerate(batch):
                img_path_str = str(img_path)
                
                # Apply filename filter first (doesn't require label file)
                if self.filter_by_name_enabled and self.filter_name_text:
                    filename = img_path.name
                    search_text = self.filter_name_text
                    if not self.filter_name_case_sensitive:
                        filename = filename.lower()
                        search_text = search_text.lower()
                    if search_text not in filename:
                        continue

                # Review state. A guard here rather than an entry in
                # `requires_labels`, so an unlabelled image can still show up
                # as "not reviewed" instead of vanishing from the working set.
                if (self.filter_by_review_enabled
                        and self.filter_review_state in ('reviewed', 'unreviewed')):
                    want = self.filter_review_state == 'reviewed'
                    if self.is_reviewed(img_path) != want:
                        continue

                # If no label-based filters, add the image
                if not requires_labels:
                    self.filtered_image_paths.append(img_path)
                else:
                    # Find label path - optimized lookup
                    label_path = None
                    if self.label_folder:
                        label_path = Path(self.label_folder) / f"{img_path.stem}.txt"
                    else:
                        # Fast lookup using pre-computed mapping
                        for img_folder, lbl_folder in label_folder_map.items():
                            if img_path_str.startswith(img_folder):
                                label_path = Path(lbl_folder) / f"{img_path.stem}.txt"
                                break
                    
                    # Check if label exists - use cache or pre-built set
                    if label_path:
                        has_label = (img_path_str in self.labels_cache or 
                                   img_path_str in has_label_set or
                                   (not has_label_set and label_path.exists()))
                        
                        if has_label or include_unlabelled:
                            total_checked += 1
                            if self.image_passes_filters(img_path, label_path):
                                self.filtered_image_paths.append(img_path)
                
                # Progress feedback - less frequent updates
                current_idx = batch_idx + i + 1
                if current_idx % ui_update_interval == 0 or current_idx == total_images:
                    elapsed = time.time() - start_time
                    progress = (current_idx / total_images) * 100
                    if current_idx > 0:
                        rate = elapsed / current_idx
                        remaining = total_images - current_idx
                        eta = rate * remaining
                        eta_str = time.strftime('%H:%M:%S', time.gmtime(eta))
                    else:
                        eta_str = '--:--:--'
                    elapsed_str = time.strftime('%H:%M:%S', time.gmtime(elapsed))
                    self.progress_var.set(progress)
                    self.filter_result_var.set(f"Filtering: {current_idx}/{total_images} | Elapsed: {elapsed_str} | ETA: {eta_str}")
                    self.root.update_idletasks()
        
        self.current_image_index = 0 if self.filtered_image_paths else -1
        self.progress_var.set(100)
        if self.current_image_index >= 0:
            self.load_image()
        else:
            self.current_image = None
            self.canvas.delete("all")
            self.canvas.create_text(
                self.canvas.winfo_width() // 2, 
                self.canvas.winfo_height() // 2,
                text="No images match the current filters",
                fill="white", font=("Arial", 14)
            )
        self.update_counter()
        count = len(self.filtered_image_paths)
        total = len(self.image_paths)
        if requires_labels:
            # Every label-based filter, not just three of them: an overlap-only
            # run used to report "Showing all N images", which reads as if no
            # filter had been applied at all.
            noun = "images" if include_unlabelled else "labeled images"
            message = f"Found: {count}/{total_checked} {noun}"
            if self.filter_by_iou_enabled:
                if self._iou_not_inferred:
                    message += f" · {self._iou_not_inferred:,} not inferred"
                # The canvas still filters at the display slider; say so, or a
                # selected frame can look clean for no visible reason.
                shown = getattr(self, 'prediction_conf', None)
                if shown is not None and shown > self.filter_iou_conf_lo + 1e-9:
                    message += f" · canvas shows ≥{shown:.2f}"
            self.filter_result_var.set(message)
        elif self.filter_by_name_enabled:
            self.filter_result_var.set(f"Found: {count}/{total} images matching '{self.filter_name_text}'")
        else:
            self.filter_result_var.set(f"Showing all {count} images")
        self.update_status(f"Filter applied: {count}/{total} images match")
        # The inference scope is the filtered set, so its denominator moved.
        self.update_inference_coverage()

    def toggle_iou_filter(self):
        self.filter_by_iou_enabled = self.filter_iou_var.get()
        if self.filter_by_iou_enabled:
            # Enable threshold entry
            pass  # (Entry is always enabled for now)

    def _image_size(self, img_path_str):
        """(width, height) for an image, honouring EXIF orientation.

        cv2.imread applies EXIF rotation but PIL's raw `.size` does not, so the
        two disagree by a transpose on rotated phone photos -- which silently
        produced transposed pixel boxes in the filters and statistics. Applying
        `exif_transpose` here makes this agree with the editor's geometry.
        """
        cached = self.image_dimensions_cache.get(img_path_str)
        if cached is not None:
            return cached
        try:
            # Header only. `ImageOps.exif_transpose()` reads like the obvious
            # call here, but it DECODES and rotates the whole frame to hand back
            # a transformed copy -- measured at 4.51ms/frame against 3.42ms for
            # a full `cv2.imread`, i.e. SLOWER than just decoding. Reading the
            # header alone is 0.03ms.
            # Orientations 5-8 are the quarter turns, so for dimensions alone a
            # swap is the entire transform.
            from PIL import Image
            with Image.open(img_path_str) as img:
                size = img.size
                if img.getexif().get(274, 1) in (5, 6, 7, 8):
                    size = (size[1], size[0])
        except Exception:
            img = cv2.imread(img_path_str, cv2.IMREAD_UNCHANGED)
            if img is None:
                return None
            size = (img.shape[1], img.shape[0])
        self.image_dimensions_cache[img_path_str] = size
        return size

    @staticmethod
    def _label_stamp(label_path):
        """(mtime_ns, size) for a label file, or None if it is not there.

        Size alone would miss the commonest edit of all -- reassigning a class
        rewrites one byte and keeps the length -- so the mtime carries the work.
        """
        try:
            st = os.stat(label_path)
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size)

    def _labels_cache_fresh(self, img_path_str, label_path):
        """Whether the cached parse still describes the file on disk."""
        stamp = self._labels_cache_stat.get(img_path_str)
        return stamp is not None and stamp == self._label_stamp(label_path)

    def _stamp_labels_cache(self, img_path_str, label_path):
        """Record that `labels_cache[img_path_str]` matches the file right now.

        Every writer of `labels_cache` must call this, otherwise its entry reads
        as permanently stale and the cache stops saving anything. Forgetting is
        merely slow, never wrong -- which is the right way round.
        """
        stamp = self._label_stamp(label_path)
        if stamp is None:
            self._labels_cache_stat.pop(img_path_str, None)
        else:
            self._labels_cache_stat[img_path_str] = stamp

    def get_label_boxes(self, img_path_str, label_path):
        """Return label boxes for an image as (cls_id, x1, y1, x2, y2) tuples."""
        # Keyed on the path alone, this used to serve whatever it parsed first.
        # Exporting labels, editing them elsewhere and importing them back is
        # the normal round trip here, and every filter kept reporting the
        # pre-import contents until the app was restarted.
        cached = self.labels_cache.get(img_path_str)
        if cached is not None and self._labels_cache_fresh(img_path_str, label_path):
            return [(l[0], l[1], l[2], l[3], l[4]) for l in cached]

        size = self._image_size(img_path_str)
        if size is None:
            return []
        img_width, img_height = size

        boxes, cache_rows = [], []
        for ln in _labelio.read_label_file(label_path):
            if not ln.parsed:
                continue
            cx, cy, w, h = ln.bbox
            x1, y1, x2, y2 = _geom.yolo_to_pixel(cx, cy, w, h, img_width, img_height)
            boxes.append((ln.cls_id, x1, y1, x2, y2))
            cache_rows.append((ln.cls_id, x1, y1, x2, y2, (x2 - x1) * (y2 - y1)))

        # Populate the cache. Previously this method READ labels_cache but never
        # wrote it, so every "Apply Filters" re-opened and re-parsed every label
        # file in the dataset -- 30-90s per click on 50k images.
        self.labels_cache[img_path_str] = cache_rows
        self._stamp_labels_cache(img_path_str, label_path)
        return boxes

    def _begin_iou_filter_pass(self):
        """Per-Apply state for the IoU filter: computed once, not per image."""
        self._iou_not_inferred = 0
        self._iou_filter_checkable = (self._checkable_classes()
                                      if self.filter_by_iou_enabled else None)

    def _iou_filter_passes(self, img_path, label_boxes):
        """Whether labels and predictions disagree here, in the chosen direction.

        Unmatched label: no prediction at or above the floor -- of ANY class,
        mapped or not -- overlaps it at the matching IoU. This is geometry, so
        unmapped boxes count: dropping them first is what fabricated unmatched
        labels before. The upper confidence bound plays no part, because a
        ceiling must never hide a prediction from matching.

        Unmatched prediction: a MAPPED prediction inside the confidence range
        that overlaps no label at the matching IoU -- an object nobody
        labelled. Unmapped boxes are excluded, or every class the dataset does
        not care about would be flagged.
        """
        raw = self._peek_cached_predictions(img_path, promote=False)
        if raw is None:
            # Never inferred. "Unknown" must not pass as "the model saw nothing".
            self._iou_not_inferred += 1
            return False

        lo, hi = self.filter_iou_conf_lo, self.filter_iou_conf_hi
        match = self.filter_iou_threshold
        cmap = getattr(self, 'prediction_class_map', None)
        preds = []
        for b in raw:
            conf = float(b[5]) if len(b) > 5 else 1.0
            if conf < lo:
                continue
            cls = cmap.translate(b[0]) if cmap is not None else b[0]
            preds.append((cls, conf, b[1], b[2], b[3], b[4]))

        direction = getattr(self, 'filter_iou_direction', 'either')
        if direction in ('labels', 'either'):
            checkable = getattr(self, '_iou_filter_checkable', None)
            for cls, x1, y1, x2, y2 in label_boxes:
                if checkable is not None and int(cls) not in checkable:
                    continue
                if not _badscan.candidates((x1, y1, x2, y2), preds, match):
                    return True
        if direction in ('predictions', 'either'):
            for pred in preds:
                if pred[0] is None or pred[1] > hi:
                    continue
                if not any(_geom.iou_xyxy(pred[2:6], lb[1:5]) >= match
                           for lb in label_boxes):
                    return True
        return False

    def image_passes_filters(self, img_path, label_path):
        img_path_str = str(img_path)
        
        # Early exit if no label-based filters are enabled
        if not (self.filter_by_class_enabled or self.filter_by_size_enabled or
                self.filter_by_iou_enabled or self.filter_by_class_presence_enabled or
                self.filter_by_overlap_enabled or self.filter_by_relsize_enabled):
            return True
        
        # Label boxes (uses cache if available)
        label_boxes = self.get_label_boxes(img_path_str, label_path)
        
        # Early exit if no boxes and filters require boxes
        if not label_boxes:
            if (self.filter_by_class_enabled or self.filter_by_size_enabled or
                self.filter_by_class_presence_enabled or self.filter_by_overlap_enabled or
                self.filter_by_relsize_enabled):
                return False
        
        # Class presence/absence filter (check first - most specific and fast)
        if self.filter_by_class_presence_enabled:
            # Get all class IDs present in this image (single pass)
            present_classes = set(box[0] for box in label_boxes)
            
            # Check must-have classes: all must be present
            if self.filter_must_have_classes:
                if not self.filter_must_have_classes.issubset(present_classes):
                    return False
            
            # Check must-not-have classes: none should be present
            if self.filter_must_not_have_classes:
                if self.filter_must_not_have_classes.intersection(present_classes):
                    return False
        
        # Class/size filter (needs to check individual boxes)
        if (self.filter_by_class_enabled or self.filter_by_size_enabled or
                self.filter_by_relsize_enabled):
            # Relative size needs the frame's own dimensions. One cached
            # header read for the image, not one per box.
            img_w = img_h = 0
            if self.filter_by_relsize_enabled:
                size = self._image_size(img_path_str)
                if size is None:
                    return False    # no dimensions -> relative size is unknowable
                img_w, img_h = size

            match_found = False
            for box in label_boxes:
                cls_id, x1, y1, x2, y2 = box

                # Only compute area if size filter is enabled
                if self.filter_by_size_enabled:
                    box_area = (x2 - x1) * (y2 - y1)
                    size_match = self.filter_min_size <= box_area <= self.filter_max_size
                else:
                    size_match = True

                if self.filter_by_relsize_enabled and img_w and img_h:
                    w_pct = 100.0 * (x2 - x1) / img_w
                    h_pct = 100.0 * (y2 - y1) / img_h
                    rel_match = (self.filter_min_w_pct <= w_pct <= self.filter_max_w_pct and
                                 self.filter_min_h_pct <= h_pct <= self.filter_max_h_pct)
                else:
                    rel_match = True

                class_match = (not self.filter_by_class_enabled) or (cls_id == self.filter_class_id)

                # Every active condition must hold on the SAME box, matching
                # the existing class+size behaviour: an image with one wide box
                # and one tall box does not satisfy "wide AND tall".
                if class_match and size_match and rel_match:
                    match_found = True
                    break

            if not match_found:
                return False
        
        # Label/Prediction IoU (most expensive - check last)
        if self.filter_by_iou_enabled:
            if not self._iou_filter_passes(img_path, label_boxes):
                return False

        # Overlapping boxes filter (quality control). Which pairs count is set
        # by `filter_overlap_scope`: different-class catches one object labelled
        # as two things, same-class catches one object labelled twice.
        if self.filter_by_overlap_enabled:
            has_overlap = False
            # Check all pairs of boxes
            for i, box1 in enumerate(label_boxes):
                cls1, x1_1, y1_1, x2_1, y2_1 = box1
                for j, box2 in enumerate(label_boxes):
                    if i >= j:  # Skip same box and already-checked pairs
                        continue
                    cls2, x1_2, y1_2, x2_2, y2_2 = box2

                    if self.overlap_pair_counts(cls1, cls2):
                        iou = self.calculate_iou((x1_1, y1_1, x2_1, y2_1), (x1_2, y1_2, x2_2, y2_2))
                        if self.overlap_iou_in_range(iou):
                            has_overlap = True
                            break
                if has_overlap:
                    break

            if not has_overlap:
                return False
        
        return True

